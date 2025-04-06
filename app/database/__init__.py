from pathlib import Path

from app.database.database import AttendifyDatabase
from app.database import models


db = AttendifyDatabase(Path("./"))
