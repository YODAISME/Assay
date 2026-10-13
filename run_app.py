import webbrowser
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  ASSAY TALENT INTELLIGENCE PLATFORM — LIQUID LIGHT")
    print("=" * 60)
    print("  Server URL: http://localhost:8000")
    print("=" * 60)
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=False)
