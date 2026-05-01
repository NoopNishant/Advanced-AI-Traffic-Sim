# 🚦 TrafficSim

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![SUMO](https://img.shields.io/badge/Eclipse_SUMO-000000?style=for-the-badge&logo=eclipse&logoColor=white)

TrafficSim is an advanced, AI-powered smart intersection simulator. Leveraging SUMO, YOLOv8 computer vision, and a headless Pygame engine, it manages real-time traffic flow, VRU (Vulnerable Road User) protection, and emergency vehicle routing. The project features a premium, interactive Streamlit web dashboard for dynamic control and live monitoring.

## ✨ Key Features

- **🧠 Edge AI Vision:** Integrates Ultralytics YOLOv8 for real-time emergency vehicle detection via camera feeds.
- **🚑 Acoustic Preemption:** Automatically detects incoming ambulances and creates an isolated green wave to clear the intersection.
- **🚚 Eco-Routing & Platoon Dispersal:** Prioritizes heavy vehicles (trucks) to minimize emissions from starting/stopping and disperses large vehicle platoons efficiently.
- **🚶 VRU Collision Lockdown:** Predicts pedestrian trajectories and triggers an all-red safety lockdown if a collision is imminent.
- **🌩️ Dynamic Environment Simulation:** Includes visual and logic-based simulated weather conditions (like Fog) which degrade sensor activation ranges.
- **🌐 Web-Based Dashboard:** Fully hosted on Streamlit with a premium glassmorphic UI, allowing you to trigger manual vehicle spawns and environmental changes in real-time.

---

## 🚀 Running Locally

### Prerequisites
1. **Python 3.8+**
2. **Eclipse SUMO** (Simulation of Urban MObility) must be installed on your system. 
   - *Windows:* Download the installer from the [official site](https://eclipse.dev/sumo/).
   - *Linux:* `sudo apt-get install sumo sumo-tools sumo-doc`

### Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/NexusPro_TrafficSim.git
   cd NexusPro_TrafficSim
   ```
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

### Execution
Run the Streamlit application:
```bash
python -m streamlit run app.py
```
The application will automatically launch in your default web browser at `http://localhost:8501`.

---

## ☁️ Free Cloud Deployment (Streamlit Community Cloud)

This project has been specifically designed to run on **Streamlit Community Cloud** without requiring a paid server.

1. Push your code to a public GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io/) and log in with your GitHub account.
3. Click **New App** and select your repository.
4. Set the **Main file path** to `app.py`.
5. Click **Deploy!**

> **Note:** The included `packages.txt` file automatically instructs the Streamlit servers to install the necessary `sumo` and `sumo-tools` Debian packages via `apt-get` before launching your application.

---

## 📁 Project Structure

```text
NexusPro_TrafficSim/
├── app.py                  # Main Streamlit web dashboard & UI engine
├── config/
│   ├── sim.sumocfg         # SUMO Configuration file
│   ├── map.net.xml         # Road network geometry
│   └── traffic.rou.xml     # Traffic routing definitions
├── logic/
│   ├── ai_controller.py    # Core AI logic and headless Pygame renderer
│   └── yolov8n.pt          # Pre-trained YOLOv8 neural network weights
├── packages.txt            # System dependencies for Streamlit Cloud (SUMO)
├── requirements.txt        # Python library dependencies
└── README.md               # Project documentation
```

---

