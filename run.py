import argparse
import os
from app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run Aptiva locally')
    parser.add_argument('--demo', action='store_true', help='Explicitly use in-memory storage, ignoring Supabase settings')
    args = parser.parse_args()
    if args.demo:
        os.environ['DATABASE_MODE'] = 'demo'

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
