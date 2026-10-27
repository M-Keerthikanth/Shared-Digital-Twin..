# Shared Digital Twin Dashboard for MSME Industrial Clusters (Micro Project 6)
Python (Flask) + SQLite. Login: admin / admin123  (or manager / manager123)

Run on your PC:   pip install -r requirements.txt   then   python app.py   -> http://127.0.0.1:5000

Deploy on Render:
1. Upload these 3 files (app.py, requirements.txt, README.md) to a new GitHub repository.
2. On render.com: New + -> Web Service -> connect the repository.
3. Runtime: Python 3 | Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app --workers 1 -b 0.0.0.0:$PORT
4. Choose the Free plan -> Create Web Service. Open the URL Render gives you.
Note: free plan data resets when the service restarts (SQLite file is temporary) and the site sleeps when idle.
