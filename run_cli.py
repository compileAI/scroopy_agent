#!/usr/bin/env python3
"""
Simple launcher for Scroopy Interactive CLI
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment from {env_path}")
    else:
        print(f"⚠️ No .env file found at {env_path}")
except ImportError:
    print("⚠️ python-dotenv not installed - you may need to set environment variables manually")

# Import and run
try:
    from cli.interactive import main
    print("🚀 Starting Scroopy Interactive CLI...\n")
    main()
except ImportError as e:
    print(f"❌ Failed to import CLI: {e}")
    print("\nTry installing dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)
except KeyboardInterrupt:
    print("\n👋 Goodbye!")
    sys.exit(0) 