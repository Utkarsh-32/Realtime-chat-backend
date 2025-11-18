from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Chat app backend is running"}
