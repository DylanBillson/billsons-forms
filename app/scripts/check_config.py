from app.core.config import settings


def main() -> None:
    errors = settings.production_errors() if settings.app_env.lower() == "production" else []
    if errors:
        raise SystemExit("Invalid production configuration:\n- " + "\n- ".join(errors))
    print("configuration valid")


if __name__ == "__main__":
    main()
