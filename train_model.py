from floodguard.risk_model import train_and_save_model
from floodguard.seed_definitions import build_seed_data


def main() -> None:
    data = build_seed_data()
    train_and_save_model(data["rainfall_river_history"])
    print("Saved model to models/flood_risk_model.joblib")


if __name__ == "__main__":
    main()


 

