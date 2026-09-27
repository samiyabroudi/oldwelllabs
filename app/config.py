import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://owl:owl@localhost:5432/owl")
