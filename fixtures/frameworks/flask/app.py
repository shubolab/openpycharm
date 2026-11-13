import os

from flask import Flask

app = Flask(__name__)


@app.get("/")
def index():
    marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
    return {"framework": "flask", "marker": marker}
