# Research Agent 

An AI-powered multi-step research agent with SSE streaming, structured for performance and scalability.

##  Startup Guide

### 1. Backend Setup
Make sure you are in the root directory.

```bash
# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend
python backend/run.py
```
The API will be available at `http://localhost:8000`.

### 2. Frontend Setup
Navigate to the frontend directory.

```bash
cd frontend

# Install dependencies
npm install

# Run the development server
npm run dev
```
The application will be available at `http://localhost:5173`.

---
> [!NOTE]
> Ensure your `.env` file is configured with the necessary API keys before starting.
