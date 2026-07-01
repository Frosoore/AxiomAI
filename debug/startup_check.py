
import sys
import os
import traceback

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_db_worker():
    """Verify that DbWorker has all required signals defined on the class."""
    print("[1/4] Checking DbWorker signals...")
    try:
        from workers.db_worker import DbWorker
        
        # Signals in PySide6 are class attributes. We don't need an instance.
        required_signals = [
            'stats_loaded', 'checkpoints_loaded', 'rewind_complete',
            'universe_meta_loaded', 'stat_definitions_loaded', 'entities_loaded',
            'rules_loaded', 'lore_book_loaded', 'scheduled_events_loaded',
            'personas_loaded', 'library_loaded', 'saves_loaded',
            'history_loaded', 'modifiers_ticked', 'variant_updated',
            'full_universe_loaded',
            'save_complete', 'error_occurred', 'status_update'
        ]
        
        missing = []
        for sig in required_signals:
            if not hasattr(DbWorker, sig):
                missing.append(sig)
        
        if missing:
            print(f"FAILED: Missing signals in DbWorker class: {missing}")
            return False
        
        print("SUCCESS: DbWorker signals verified.")
        return True
            
    except Exception as e:
        print(f"FAILED: Unexpected error checking DbWorker: {e}")
        return False

def check_schema():
    """Verify that the schema producing function includes the new spatial tables."""
    print("[2/4] Verifying database schema...")
    try:
        from axiom.schema import EXPECTED_TABLES
        new_tables = ["Locations", "Location_Connections"]
        missing = [t for t in new_tables if t not in EXPECTED_TABLES]
        if missing:
            print(f"FAILED: Missing spatial tables in EXPECTED_TABLES: {missing}")
            return False
        print("SUCCESS: Spatial tables present in schema definition.")
        return True
    except Exception as e:
        print(f"FAILED: Unexpected error checking schema: {e}")
        return False

def check_system_dependencies():
    """Verify system-level libraries required by PySide6 / Qt are present on Linux."""
    if sys.platform.startswith("linux"):
        # If running in headless mode (e.g., CI or CLI play), skip checking GUI dependencies
        qpa = os.environ.get("QT_QPA_PLATFORM", "").lower()
        if qpa in ["offscreen", "minimal"]:
            return True

        print("[3/4] Verifying system GUI libraries...")
        # Check libxcb-cursor.so.0
        has_xcb_cursor = True
        try:
            import subprocess
            out = subprocess.check_output(["/sbin/ldconfig", "-p"], stderr=subprocess.DEVNULL)
            if b"libxcb-cursor.so.0" not in out:
                has_xcb_cursor = False
        except Exception:
            try:
                import subprocess
                out = subprocess.check_output(["ldconfig", "-p"], stderr=subprocess.DEVNULL)
                if b"libxcb-cursor.so.0" not in out:
                    has_xcb_cursor = False
            except Exception:
                try:
                    import ctypes.util
                    if not ctypes.util.find_library("xcb-cursor"):
                        has_xcb_cursor = False
                except Exception:
                    pass
        
        if not has_xcb_cursor:
            print("  FAILED: libxcb-cursor0 is missing on your system!")
            print("  This library is required for the PySide6 GUI to start under X11/Wayland.")
            print("  HINT: Please install it using your system package manager:")
            print("    Ubuntu/Debian/Mint: sudo apt update && sudo apt install libxcb-cursor0")
            print("    Fedora/RHEL:        sudo dnf install xcb-cursor")
            print("    Arch/Manjaro:       sudo pacman -S xcb-cursor")
            return False
            
        print("SUCCESS: System GUI libraries verified.")
    return True

def check_imports():
    """Verify core imports aren't broken."""
    print("[4/4] Verifying core imports...")
    core_modules = [
        ('PySide6.QtWidgets', 'pyside6'),
        ('google.genai', 'google-genai'),
        ('PIL', 'pillow'),
        ('axiom.arbitrator', 'axiom'),
        ('axiom.schema', 'axiom'),
        ('axiom.backends.base', 'axiom'),
        ('ui.main_window', 'ui')
    ]
    
    all_ok = True
    for mod_name, pkg_name in core_modules:
        try:
            __import__(mod_name)
            print(f"  OK: {mod_name}")
        except ImportError as e:
            print(f"  FAILED: Could not import '{mod_name}' (package: {pkg_name})")
            print(f"  Error: {e}")
            if pkg_name in ['pyside6', 'chromadb', 'sentence-transformers']:
                print(f"  HINT: Try running 'pip install {pkg_name}' manually in the .venv")
            all_ok = False
        except Exception as e:
            print(f"  FAILED: Unexpected error importing '{mod_name}': {e}")
            all_ok = False
            
    if all_ok:
        print("SUCCESS: Core imports verified.")
    return all_ok

def run_checks():
    """Main entry point for startup validation, called by main.py."""
    print("--- Axiom AI Startup Validation ---")
    
    if not check_db_worker():
        sys.exit(1)

    if not check_schema():
        sys.exit(1)

    if not check_system_dependencies():
        sys.exit(1)
        
    if not check_imports():
        print("\nERROR: Some dependencies are missing or broken.")
        if sys.platform != "win32":
            print("If you are on Linux, ensure you have installed system requirements:")
            print("  sudo apt install python3-venv libxcb-cursor0")
        
        print("\nTry recreating the virtual environment:")
        if sys.platform == "win32":
            print("  rd /s /q .venv && run.bat")
        else:
            print("  rm -rf .venv && bash run.sh")
        sys.exit(1)
        
    print("--- Startup Validation Passed ---\n")

if __name__ == "__main__":
    run_checks()
