import traci
import pygame
import math
import sys
import random
import time
import cv2
from ultralytics import YOLO

# ─────────────────────────────────────────────
#  CONFIGURATION & THEME
# ─────────────────────────────────────────────
COLORS = {
    'BG':        (176, 186, 195), 'ROAD':      ( 60,  65,  70),
    'AMBULANCE': (255,  50,  80), 'RICKSHAW':  (240, 200,  50),
    'BIKE':      ( 50, 220, 200), 'DEFAULT':   (120, 100, 220),
    'TRUCK':     ( 80,  90,  80), 
    'VRU':       (255, 150,   0), 'TEXT':      ( 30,  30,  30),
    'GREEN':     ( 40, 255,  80), 'YELLOW':    (255, 200,   0), 'RED': (255, 40, 40)
}

JUNCTION_ID = "J4"
SCALE = 5
CENTER_X, CENTER_Y = 0, 0

# ── Tunable Constants ──
AMB_ACTIVATE_DIST   = 150   
AMB_HOLD_STEPS      = 40    
TRUCK_ACTIVATE_DIST = 120   
TRUCK_HOLD_STEPS    = 30    
VRU_DANGER_RADIUS   = 18    
VRU_PREDICTION_SEC  = 3.0   
VRU_HOLD_STEPS      = 60    
PLATOON_THRESHOLD   = 22    
DEMAND_BUFFER_STEPS = 40    
DEMAND_STAY_RATIO   = 0.10  # keep green until below 10% of starting queue

# ── Global State Engine ──
_active_feature         = "Normal Traffic Control"
_amb_hold_counter       = 0     
_truck_hold_counter     = 0     
_vru_hold_counter       = 0     
_demand_buffer          = DEMAND_BUFFER_STEPS
_demand_active_edge     = None
_demand_start_count     = 0
_demand_all_red_timer   = 0
_demand_pending_edge    = None
_fog_active             = False 
_vision_msg_timer       = 0     

# Custom Indian Split-Phasing 
_cycle_idx = 0
_cycle_timer = 200 
PHASE_DURATIONS = [250, 40, 250, 40, 250, 40, 250, 40] 
NORMAL_PHASES = [
    "GGGGGrrrrrrrrrrrrrrr", # 0: North Green
    "yyyyyrrrrrrrrrrrrrrr", # 1: North Yellow
    "rrrrrGGGGGrrrrrrrrrr", # 2: East Green
    "rrrrryyyyyrrrrrrrrrr", # 3: East Yellow
    "rrrrrrrrrrGGGGGrrrrr", # 4: South Green
    "rrrrrrrrrryyyyyrrrrr", # 5: South Yellow
    "rrrrrrrrrrrrrrrGGGGG", # 6: West Green
    "rrrrrrrrrrrrrrryyyyy"  # 7: West Yellow
]

pygame.font.init()
SYS_FONT = pygame.font.SysFont("Arial", 14, bold=True)
UI_FONT = pygame.font.SysFont("Arial", 22, bold=True)

# ─────────────────────────────────────────────
#  MANUAL INJECTIONS
# ─────────────────────────────────────────────
def spawn_manual_vehicle(v_type="ambulance"):
    edges = ["-E4", "-E5", "-E6", "-E7"]
    edge = random.choice(edges)
    v_id = f"manual_{v_type}_{int(traci.simulation.getTime())}"
    try:
        dest_map = {"-E4": "E6", "-E6": "E4", "-E5": "E7", "-E7": "E5"}
        traci.vehicle.add(v_id, routeID="", typeID=v_type)
        traci.vehicle.setRoute(v_id, [edge, dest_map[edge]])
        traci.vehicle.moveToLane(v_id, edge + "_0", 0) 
    except: pass

# ─────────────────────────────────────────────
#  AI FEATURES & CONTROLLER
# ─────────────────────────────────────────────
def _state_from_edge(edge):
    if "-E4" in edge: return NORMAL_PHASES[0]
    elif "-E5" in edge: return NORMAL_PHASES[2]
    elif "-E6" in edge: return NORMAL_PHASES[4]
    elif "-E7" in edge: return NORMAL_PHASES[6]
    return "rrrrrrrrrrrrrrrrrrrr"

def feature_acoustic_preemption(vehicles):
    global _amb_hold_counter, _truck_hold_counter, _active_feature, _cycle_timer, _demand_buffer, _fog_active, _demand_active_edge

    active_amb_dist = AMB_ACTIVATE_DIST * 0.5 if _fog_active else AMB_ACTIVATE_DIST
    active_truck_dist = TRUCK_ACTIVATE_DIST * 0.5 if _fog_active else TRUCK_ACTIVATE_DIST

    for v_id in vehicles:
        if traci.vehicle.getTypeID(v_id) != "ambulance": continue
        edge = traci.vehicle.getRoadID(v_id)
        x, y = traci.vehicle.getPosition(v_id)

        if not edge.startswith(":") and math.hypot(x - CENTER_X, y - CENTER_Y) < active_amb_dist:
            state = _state_from_edge(edge)
            traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, state)
            _amb_hold_counter = AMB_HOLD_STEPS
            _cycle_timer = 50
            _active_feature = "EMERGENCY: ISOLATED GREEN WAVE"
            _demand_buffer = DEMAND_BUFFER_STEPS
            _demand_active_edge = None
            return True

        if edge.startswith(":") and _amb_hold_counter > 0:
            _amb_hold_counter -= 1
            _active_feature = "EMERGENCY: CLEARING INTERSECTION"
            _demand_buffer = DEMAND_BUFFER_STEPS
            _demand_active_edge = None
            return True

    if _amb_hold_counter > 0:
        _amb_hold_counter -= 1
        _demand_buffer = DEMAND_BUFFER_STEPS
        return True

    for v_id in vehicles:
        if traci.vehicle.getTypeID(v_id) != "truck": continue
        edge = traci.vehicle.getRoadID(v_id)
        x, y = traci.vehicle.getPosition(v_id)

        if not edge.startswith(":") and math.hypot(x - CENTER_X, y - CENTER_Y) < active_truck_dist:
            state = _state_from_edge(edge)
            traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, state)
            _truck_hold_counter = TRUCK_HOLD_STEPS
            _cycle_timer = 50
            _active_feature = "TRUCK PRIORITY: MINIMIZE STOPPING"
            _demand_buffer = DEMAND_BUFFER_STEPS
            _demand_active_edge = None
            return True

        if edge.startswith(":") and _truck_hold_counter > 0:
            _truck_hold_counter -= 1
            _active_feature = "TRUCK PRIORITY: EXITING INTERSECTION"
            _demand_buffer = DEMAND_BUFFER_STEPS
            _demand_active_edge = None
            return True

    if _truck_hold_counter > 0:
        _truck_hold_counter -= 1
        _demand_buffer = DEMAND_BUFFER_STEPS
        return True

    return False

def feature_vru_protection(pedestrians):
    global _vru_hold_counter, _active_feature, _demand_active_edge
    alerts = []
    for p_id in pedestrians:
        x, y = traci.person.getPosition(p_id)
        angle, speed = math.radians(traci.person.getAngle(p_id)), traci.person.getSpeed(p_id)
        fx, fy = x + math.sin(angle)*speed*VRU_PREDICTION_SEC, y + math.cos(angle)*speed*VRU_PREDICTION_SEC
        if abs(fx - CENTER_X) < VRU_DANGER_RADIUS and abs(fy - CENTER_Y) < VRU_DANGER_RADIUS:
            _vru_hold_counter = VRU_HOLD_STEPS
            alerts.append((x, y, fx, fy))

    if _vru_hold_counter > 0:
        traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, "rrrrrrrrrrrrrrrrrrrr")
        _vru_hold_counter -= 1
        _active_feature = "VRU COLLISION LOCKDOWN (ALL RED)"
        _demand_active_edge = None # Reset demand logic when pedestrian interrupts
        return alerts or [None]
    return []

def feature_eco_routing(vehicles):
    global _active_feature
    truck_present = False
    for v_id in vehicles:
        if traci.vehicle.getTypeID(v_id) == "truck":
            truck_present = True
            try:
                if traci.vehicle.getLaneIndex(v_id) != 0:
                    traci.vehicle.changeLane(v_id, 0, 2.0)
            except: pass
            
    if truck_present and "Standard" in _active_feature:
        _active_feature = "ECO-ROUTING: MANAGING HEAVY EMISSIONS"

def feature_platoon_dispersal():
    global _cycle_timer, _active_feature
    best_edge, best_count = None, 0
    for edge in ["-E4", "-E5", "-E6", "-E7"]:
        c = traci.edge.getLastStepVehicleNumber(edge)
        if c > best_count: best_count, best_edge = c, edge

    if best_count >= PLATOON_THRESHOLD:
        target_idx = {"-E4": 0, "-E5": 2, "-E6": 4, "-E7": 6}.get(best_edge)
        if _cycle_idx == target_idx and _cycle_timer < 50:
            _cycle_timer += 100 
            _active_feature = "PLATOON DISPERSAL: EXTENDING GREEN"
            return True
    return False

def feature_demand_green(vehicles):
    global _cycle_idx, _cycle_timer, _active_feature, _demand_buffer, _demand_active_edge, _demand_start_count, _demand_all_red_timer, _demand_pending_edge

    edge_counts = {edge: traci.edge.getLastStepVehicleNumber(edge) for edge in ["-E4", "-E5", "-E6", "-E7"]}
    best_edge = max(edge_counts, key=edge_counts.get)
    best_count = edge_counts.get(best_edge, 0)

    # Only run demand logic if there is meaningful traffic
    if best_count < 4:
        _demand_active_edge = None
        return False

    phase_to_edge = {0: "-E4", 2: "-E5", 4: "-E6", 6: "-E7"}
    current_edge = phase_to_edge.get(_cycle_idx)
    current_count = edge_counts.get(current_edge, 0) if current_edge else 0

    # 1. Handle Pending All-Red Safety Transition
    if _demand_pending_edge:
        if _demand_all_red_timer > 0:
            _demand_all_red_timer -= 1
            traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, "rrrrrrrrrrrrrrrrrrrr")
            _active_feature = "DEMAND SHIFT: ALL RED SAFETY BUFFER"
            return True 
        
        # Buffer done, set to new Green Phase
        target_idx = {"-E4": 0, "-E5": 2, "-E6": 4, "-E7": 6}[_demand_pending_edge]
        _cycle_idx = target_idx
        _cycle_timer = PHASE_DURATIONS[target_idx] 
        traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, NORMAL_PHASES[target_idx])
        
        _demand_active_edge = _demand_pending_edge
        _demand_start_count = max(edge_counts.get(_demand_pending_edge, 0), 1)
        _demand_pending_edge = None
        return True

    # 2. Hold All-Red recovery if coming back from an Emergency or VRU
    current_state = traci.trafficlight.getRedYellowGreenState(JUNCTION_ID)
    if current_state == "rrrrrrrrrrrrrrrrrrrr" and _demand_buffer > 0:
        _demand_buffer -= 1
        return True # Fix: MUST return True to hold the safety state

    # 3. Do NOT interrupt Yellow Light transitions! Let normal traffic finish them.
    if _cycle_idx % 2 != 0: 
        return False 

    # 4. If no active demand edge is set, start the transition to the heaviest lane
    if _demand_active_edge is None:
        if current_edge == best_edge:
            # We are already on the best edge, just lock it in.
            _demand_active_edge = current_edge
            _demand_start_count = max(best_count, 1)
            return True
        else:
            # Force transition: Setup pending edge and force cycle to 0 so Yellow light starts next frame
            _cycle_timer = 0 
            _demand_pending_edge = best_edge
            _demand_all_red_timer = DEMAND_BUFFER_STEPS
            return False 

    # 5. THE 90% CLEARANCE LOGIC
    if current_edge == _demand_active_edge:
        target_remaining = math.ceil(DEMAND_STAY_RATIO * _demand_start_count)
        
        if current_count > target_remaining and current_count > 2:
            # Queue NOT cleared yet. Lock the green light!
            traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, NORMAL_PHASES[_cycle_idx])
            _active_feature = f"CLEARING QUEUE: {current_count} cars left"
            _cycle_timer = PHASE_DURATIONS[_cycle_idx] # Prevent standard timer from counting down
            return True
        else:
            # 90% Cleared! Time to switch to next lane. Force Yellow light.
            _demand_active_edge = None
            _cycle_timer = 0 
            return False

    return False

def update_normal_traffic():
    global _cycle_idx, _cycle_timer, _active_feature
    _active_feature = "Standard 4-Phase (Split) Control"
    _cycle_timer -= 1
    if _cycle_timer <= 0:
        _cycle_idx = (_cycle_idx + 1) % 8
        _cycle_timer = PHASE_DURATIONS[_cycle_idx]
    traci.trafficlight.setRedYellowGreenState(JUNCTION_ID, NORMAL_PHASES[_cycle_idx])

# ─────────────────────────────────────────────
#  DIRECTIONAL RENDERING & UI
# ─────────────────────────────────────────────
def draw_directional_light(screen, x, y, state_chars, orientation='horizontal', label=""):
    if orientation == 'vertical':
        pygame.draw.rect(screen, (40, 40, 45), (x, y, 26, 76), border_radius=4)
        r_state, s_state, l_state = state_chars[0], state_chars[1], state_chars[4] if len(state_chars) > 4 else 'r'
        for i, (lbl, state) in enumerate([("L", l_state), ("S", s_state), ("R", r_state)]):
            bx, by = x + 13, y + 13 + (i * 25)
            color = COLORS['GREEN'] if state in ['G', 'g'] else (COLORS['YELLOW'] if state in ['y', 'Y'] else COLORS['RED'])
            pygame.draw.circle(screen, color, (bx, by), 9)
            text = SYS_FONT.render(lbl, True, (0, 0, 0))
            screen.blit(text, text.get_rect(center=(bx, by)))
        if label:
            txt = SYS_FONT.render(label, True, COLORS['TEXT'])
            screen.blit(txt, (x + 13 - txt.get_width()//2, y + 76 + 5))
    else:
        pygame.draw.rect(screen, (40, 40, 45), (x, y, 76, 26), border_radius=4)
        r_state, s_state, l_state = state_chars[0], state_chars[1], state_chars[4] if len(state_chars) > 4 else 'r'
        for i, (lbl, state) in enumerate([("L", l_state), ("S", s_state), ("R", r_state)]):
            bx, by = x + 13 + (i * 25), y + 13
            color = COLORS['GREEN'] if state in ['G', 'g'] else (COLORS['YELLOW'] if state in ['y', 'Y'] else COLORS['RED'])
            pygame.draw.circle(screen, color, (bx, by), 9)
            text = SYS_FONT.render(lbl, True, (0, 0, 0))
            screen.blit(text, text.get_rect(center=(bx, by)))
        if label:
            txt = SYS_FONT.render(label, True, COLORS['TEXT'])
            screen.blit(txt, (x + 38 - txt.get_width()//2, y + 26 + 5))

def draw_traffic_lights(screen):
    state = traci.trafficlight.getRedYellowGreenState(JUNCTION_ID)
    if len(state) < 20: return
    draw_directional_light(screen, 490, 200, state[0:5], orientation='vertical', label="N Lane Light")
    draw_directional_light(screen, 530, 480, state[5:10], orientation='horizontal', label="E Lane Light")
    draw_directional_light(screen, 295, 500, state[10:15], orientation='vertical', label="S Lane Light")
    draw_directional_light(screen, 200, 295, state[15:20], orientation='horizontal', label="W Lane Light")

def render_ui(screen, alerts):
    global _vision_msg_timer
    screen.fill(COLORS['BG'])
    w = 110
    pygame.draw.rect(screen, COLORS['ROAD'], (400 - w//2, 0, w, 800))
    pygame.draw.rect(screen, COLORS['ROAD'], (0, 400 - w//2, 800, w))
    
    divider_color = (255, 255, 255) 
    pygame.draw.line(screen, divider_color, (400, 0), (400, 800), 2)
    pygame.draw.line(screen, divider_color, (0, 400), (800, 400), 2)
    pygame.draw.lines(screen, divider_color, True, [(400 - w//2, 400 - w//2), (400 + w//2, 400 - w//2), (400 + w//2, 400 + w//2), (400 - w//2, 400 + w//2)], 2)
    
    draw_traffic_lights(screen)

    txt_north = SYS_FONT.render("North Lane", True, COLORS['TEXT'])
    screen.blit(txt_north, (400 - txt_north.get_width()//2, 200))
    txt_south = SYS_FONT.render("South Lane", True, COLORS['TEXT'])
    screen.blit(txt_south, (400 - txt_south.get_width()//2, 600))
    txt_east = SYS_FONT.render("East Lane", True, COLORS['TEXT'])
    screen.blit(txt_east, (600, 400 - txt_east.get_height()//2))
    txt_west = SYS_FONT.render("West Lane", True, COLORS['TEXT'])
    screen.blit(txt_west, (200 - txt_west.get_width(), 400 - txt_west.get_height()//2))

    txt1 = UI_FONT.render(f"SYSTEM STATUS: {_active_feature}", True, COLORS['TEXT'])
    screen.blit(txt1, (20, 20))
    txt2 = SYS_FONT.render("Press 'A' (Ambulance) | 'T' (Truck) | 'V' (Simulate Vision) | 'F' (Toggle Fog)", True, COLORS['TEXT'])
    screen.blit(txt2, (20, 50))

    if _vision_msg_timer > 0:
        msg = UI_FONT.render("[ EDGE AI VISION TRIGGER: TARGET DETECTED ]", True, COLORS['GREEN'])
        screen.blit(msg, (400 - msg.get_width()//2, 130))
        _vision_msg_timer -= 1

    for v_id in traci.vehicle.getIDList():
        x, y = traci.vehicle.getPosition(v_id)
        v_type = traci.vehicle.getTypeID(v_id)
        angle = traci.vehicle.getAngle(v_id)
        
        rad_angle = math.radians(angle)
        lht_shift = 14 
        rx = int((x - CENTER_X) * SCALE) + 400 + (math.cos(rad_angle) * lht_shift)
        ry = int(-(y - CENTER_Y) * SCALE) + 400 + (math.sin(rad_angle) * lht_shift)

        if v_type == "ambulance": col, len_v = COLORS['AMBULANCE'], 26
        elif v_type == "truck": col, len_v = COLORS['TRUCK'], 36 
        elif v_type == "auto_rickshaw": col, len_v = COLORS['RICKSHAW'], 18
        else: col, len_v = COLORS['DEFAULT'], 22
        
        width = 10 if v_type != "truck" else 12
        surf = pygame.Surface((width, len_v), pygame.SRCALPHA)
        pygame.draw.rect(surf, col, (0, 0, width, len_v), border_radius=3)
        rotated = pygame.transform.rotate(surf, -angle)
        screen.blit(rotated, rotated.get_rect(center=(rx, ry)))

        if v_type == "ambulance":
            p = (pygame.time.get_ticks() // 5) % 150
            pygame.draw.circle(screen, COLORS['AMBULANCE'], (rx, ry), p, 2)

    for item in alerts:
        if isinstance(item, tuple) and len(item) == 4:
            cx, cy, fx, fy = item
            s = (int((cx - CENTER_X)*SCALE)+400, int(-(cy - CENTER_Y)*SCALE)+400)
            e = (int((fx - CENTER_X)*SCALE)+400, int(-(fy - CENTER_Y)*SCALE)+400)
            pygame.draw.line(screen, COLORS['VRU'], s, e, 2)

    global _fog_active
    if _fog_active:
        fog_surf = pygame.Surface((800, 800), pygame.SRCALPHA)
        fog_surf.fill((180, 190, 200, 180)) 
        screen.blit(fog_surf, (0, 0))
        warn_txt = UI_FONT.render("WARNING: LOW VISIBILITY (SENSORS DEGRADED)", True, (255, 50, 50))
        screen.blit(warn_txt, (400 - warn_txt.get_width()//2, 100))

# ─────────────────────────────────────────────
#  HEADLESS STREAMLIT INTEGRATION
# ─────────────────────────────────────────────

# Expose global vars for Streamlit control
def set_fog(state):
    global _fog_active
    _fog_active = state

def get_fog():
    global _fog_active
    return _fog_active

def trigger_vision():
    global _vision_msg_timer
    spawn_manual_vehicle("ambulance")
    _vision_msg_timer = 90

import os

_sim_initialized = False
_screen = None
_cv_model = None
_cap = None
_last_cv_trigger = 0

def init_sim(config_path="../config/sim.sumocfg"):
    global CENTER_X, CENTER_Y, _sim_initialized, _screen, _cv_model, _cap

    # Force headless mode for Streamlit Cloud
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    
    # We render at 800x800 and scale up later for high-res
    _screen = pygame.Surface((800, 800))
    
    try:
        if not traci.isLoaded():
            traci.start(["sumo", "-c", config_path, "--step-length", "0.1"])
    except traci.exceptions.FatalTraCIError:
        traci.start(["sumo", "-c", config_path, "--step-length", "0.1"])
        
    CENTER_X, CENTER_Y = traci.junction.getPosition(JUNCTION_ID)
    _sim_initialized = True
    
    print("\n[INIT] Loading YOLOv8 Neural Network Weights...")
    try:
        _cv_model = YOLO('logic/yolov8n.pt') 
    except Exception as e:
        print(f"[WARNING] ML Model failed to load: {e}")
        _cv_model = None

def step_sim():
    global _last_cv_trigger, _vision_msg_timer

    if not _sim_initialized:
        return None

    traci.simulationStep()
    vehicles, peds = traci.vehicle.getIDList(), traci.person.getIDList()

    # ── EXPERT SYSTEM LOGIC ──
    is_p = feature_acoustic_preemption(vehicles)
    al = []
    if not is_p:
        al = feature_vru_protection(peds)
        if not al:
            feature_eco_routing(vehicles)
            if not feature_platoon_dispersal():
                if not feature_demand_green(vehicles):
                    update_normal_traffic()

    render_ui(_screen, al)

    # Convert surface to High-Res Image (1200x1200) for Streamlit
    high_res = pygame.transform.smoothscale(_screen, (1200, 1200))
    
    # Convert pygame surface to numpy array for Streamlit
    view = pygame.surfarray.array3d(high_res)
    view = view.transpose([1, 0, 2]) # swap x and y
    
    return view

def cleanup_sim():
    global _sim_initialized
    if _sim_initialized:
        traci.close()
        pygame.quit()
        _sim_initialized = False

def main():
    # Keep the original standalone functionality but adapted to the new functions
    init_sim()
    screen_display = pygame.display.set_mode((800, 800))
    clock = pygame.time.Clock()
    
    while True:
        frame = step_sim()
        if frame is None:
            break
            
        # Draw the original 800x800 surface to the display
        screen_display.blit(_screen, (0, 0))
        pygame.display.flip()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cleanup_sim()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_a: spawn_manual_vehicle("ambulance")
                if event.key == pygame.K_t: spawn_manual_vehicle("truck")
                if event.key == pygame.K_f: set_fog(not get_fog())
                if event.key == pygame.K_v: trigger_vision()
                
        clock.tick(30)
        
if __name__ == "__main__": main()
