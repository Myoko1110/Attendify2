from pathlib import Path

from app.database import models
from app.database.database import AttendifyDatabase

db = AttendifyDatabase(Path("./"))
