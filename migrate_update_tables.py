from sqlalchemy import create_engine
from app.database.models import Base

# Use a normal SQLAlchemy URL string for sqlite
DB_URL = "sqlite:///attendify.db"
engine = create_engine(DB_URL, echo=True)


def reset_database():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    reset_database()
