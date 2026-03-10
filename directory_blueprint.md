road_user_intelligence_platform/
│
├── README.md
├── master_orchestrator.md         # Orchestration plan (provided)
├── requirements.txt               # Python dependencies for all agents
├── docker-compose.yml             # Optional: for containerized MVP
│
├── config/                        # Configuration files for agents
│   ├── cameras.yaml               # Edge + RTSP camera configs
│   ├── system_config.yaml         # Global system configs
│   ├── mqtt_config.yaml           # MQTT broker info
│   ├── database_config.yaml       # PostgreSQL connection
│   └── simulation_config.yaml     # Traffic simulation parameters
│
├── agents/                        # All agent modules
│   ├── edge_vision_agent.md
│   ├── rtsp_perception_agent.md
│   ├── speed_estimation_agent.md
│   ├── violation_detection_agent.md
│   ├── data_streaming_agent.md
│   ├── backend_api_agent.md
│   ├── data_engineering_agent.md
│   ├── analytics_dashboard_agent.md
│   ├── cloud_infrastructure_agent.md
│   ├── traffic_simulation_agent.md
│   ├── trajectory_prediction_agent.md
│   └── research_evaluation_agent.md
│
├── src/                           # Python source code
│   ├── edge_vision/               # Edge Vision Agent scripts
│   │   ├── camera_capture.py
│   │   ├── detection.py
│   │   ├── tracking.py
│   │   └── publisher.py
│   │
│   ├── rtsp_perception/           # RTSP Agent scripts
│   │   ├── rtsp_ingestion.py
│   │   ├── detection.py
│   │   ├── tracking.py
│   │   └── publisher.py
│   │
│   ├── speed_estimation/
│   │   ├── speed_calc.py
│   │   └── calibration.py
│   │
│   ├── violation_detection/
│   │   └── violation_rules.py
│   │
│   ├── data_streaming/
│   │   └── mqtt_publisher.py
│   │
│   ├── backend_api/
│   │   ├── main.py
│   │   ├── models.py
│   │   └── routes.py
│   │
│   ├── data_engineering/
│   │   └── etl_pipeline.py
│   │
│   ├── analytics_dashboard/
│   │   └── dashboard_app/
│   │       ├── app.py
│   │       └── dashboards/
│   │
│   ├── traffic_simulation/
│   │   ├── simulator.py
│   │   ├── scenario_generator.py
│   │   └── visualization.py
│   │
│   ├── trajectory_prediction/
│   │   ├── model.py
│   │   ├── predict.py
│   │   └── dataset_preparation.py
│   │
│   └── research_evaluation/
│       └── evaluation_metrics.py
│
├── tests/                         # Unit & integration tests
│   ├── test_edge_vision.py
│   ├── test_rtsp_perception.py
│   ├── test_speed_estimation.py
│   ├── test_violation_detection.py
│   └── test_trajectory_prediction.py
│
├── notebooks/                      # Jupyter notebooks for experiments
│   ├── trajectory_prediction_demo.ipynb
│   ├── traffic_simulation_demo.ipynb
│   └── analytics_dashboard_demo.ipynb
│
└── docs/                           # Documentation
    ├── system_architecture.md
    ├── agent_specs.md
    └── integration_guide.md                