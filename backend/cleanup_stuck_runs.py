import os
import sys
import datetime

# Add backend directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.postgres_client import SessionLocal, AuditRun

def cleanup_stuck_runs():
    db = SessionLocal()
    try:
        # Find all runs stuck in "running" for more than 15 minutes
        cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
        stuck_runs = db.query(AuditRun).filter(
            AuditRun.status == "running",
            AuditRun.started_at < cutoff_time
        ).all()
        
        if not stuck_runs:
            print("No stuck runs found.")
            return

        print(f"Found {len(stuck_runs)} stuck runs. Updating to 'failed'...")
        
        for run in stuck_runs:
            run.status = "failed"
            # If completed_at is null, set it to the cutoff_time or now
            if not run.completed_at:
                run.completed_at = datetime.datetime.utcnow()
                
        db.commit()
        print(f"Successfully updated {len(stuck_runs)} rows.")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_stuck_runs()
