import streamlit as st
import time
import os

# We must set this before importing pygame in ai_controller
os.environ["SDL_VIDEODRIVER"] = "dummy"

from logic.ai_controller import (
    init_sim, step_sim, set_fog, get_fog, trigger_vision, spawn_manual_vehicle
)

# ─────────────────────────────────────────────
# PAGE CONFIG & CSS (Dynamic Glassmorphism)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NexusPro TrafficSim",
    page_icon="🚦",
    layout="wide"
)

def inject_custom_css():
    st.markdown("""
        <style>
        /* Animated Gradient Background */
        .stApp {
            background: linear-gradient(-45deg, #0f2027, #203a43, #2c5364, #1f4037);
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            color: #ffffff;
        }
        
        @keyframes gradientBG {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        /* Glassmorphism Sidebar */
        [data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.05) !important;
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        /* Styled Buttons */
        .stButton>button {
            width: 100%;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: white;
            border-radius: 8px;
            padding: 10px;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.4);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
            transform: translateY(-2px);
        }
        
        /* Headers */
        h1, h2, h3 {
            font-family: 'Inter', sans-serif;
            text-shadow: 0 2px 4px rgba(0,0,0,0.5);
        }
        </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────
if 'sim_started' not in st.session_state:
    try:
        init_sim(config_path="config/sim.sumocfg")
        st.session_state.sim_started = True
        st.session_state.fog = False
        st.session_state.play = True
    except Exception as e:
        st.error(f"Failed to initialize simulation: {e}")
        st.session_state.sim_started = False
        st.session_state.play = False
        st.stop() # Stop execution so user can see the error

if not st.session_state.get('sim_started', False):
    st.error("Simulation failed to start. Check the logs.")
    st.stop()

# ─────────────────────────────────────────────
# SIDEBAR CONTROLS
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("🚦 NexusPro Control Panel")
    st.markdown("Interact with the live AI simulation using the controls below.")
    
    st.markdown("---")
    st.subheader("Manual Injections")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚑 Ambulance"):
            spawn_manual_vehicle("ambulance")
    with col2:
        if st.button("🚚 Truck"):
            spawn_manual_vehicle("truck")
            
    if st.button("📸 Trigger AI Vision"):
        trigger_vision()
        
    st.markdown("---")
    st.subheader("Environment")
    
    if st.button("🌫️ Toggle Fog" if not st.session_state.fog else "☀️ Clear Fog"):
        st.session_state.fog = not st.session_state.fog
        set_fog(st.session_state.fog)
        
    st.markdown("---")
    st.subheader("Simulation State")
    if st.button("⏸️ Pause" if st.session_state.play else "▶️ Play"):
        st.session_state.play = not st.session_state.play

# ─────────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────────
st.title("NexusPro TrafficSim")
st.markdown("High-Resolution AI-Driven Traffic Management System")

# Placeholder for the high-res video frame
video_placeholder = st.empty()

# ─────────────────────────────────────────────
# SIMULATION LOOP
# ─────────────────────────────────────────────
# Run the simulation loop continuously if play is true
if st.session_state.play:
    # Use a small loop block to push updates to the UI
    # We yield to Streamlit reruns so button clicks can register
    for _ in range(5):
        frame = step_sim()
        if frame is not None:
            # frame is a (H, W, 3) numpy array
            video_placeholder.image(frame, channels="RGB", use_container_width=True)
            time.sleep(0.05)  # Cap at ~20 FPS to prevent burning CPU
        else:
            st.warning("Simulation ended or not initialized.")
            st.session_state.play = False
            break
            
    # Trigger a rerun to keep the loop going while allowing UI interaction
    st.rerun()
else:
    # Just render the last frame if paused
    frame = step_sim() # We might need a get_frame() without step, but for now just showing it paused
    if frame is not None:
        video_placeholder.image(frame, channels="RGB", use_container_width=True)
    st.info("Simulation is currently paused.")
