import os

from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def index():
    marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
    return {"framework": "fastapi", "marker": marker}
