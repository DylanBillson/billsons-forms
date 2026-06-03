import getpass

from app.auth.passwords import hash_password
from app.db.models.user import User
from app.db.session import SessionLocal


def main() -> None:
    username = input("Username: ").strip()
    display_name = input("Display name: ").strip()
    password = getpass.getpass("Password: ").strip()

    if not username or not display_name or not password:
        raise SystemExit("Username, display name and password are required.")

    db = SessionLocal()

    try:
        existing_user = db.query(User).filter(User.username == username).first()

        if existing_user:
            raise SystemExit(f"User '{username}' already exists.")

        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            is_deleted=False,
        )

        db.add(user)
        db.commit()

        print(f"Admin user '{username}' created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()