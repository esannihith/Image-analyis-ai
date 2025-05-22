import sys
import os
import traceback

# This ensures that the 'Backend' directory is on the path
# allowing 'app.crew' to be found, and then 'app.tools' etc.
# Usually, running `python test.py` from the `Backend` directory itself
# is enough, but this can make it more robust.
# Adjust if your project structure is different or if 'Backend' isn't the intended root.
# current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root = os.path.abspath(os.path.join(current_dir)) # Assumes test.py is in Backend
# if project_root not in sys.path:
#    sys.path.insert(0, project_root)

try:
    print("Attempting to import ImageAnalysisCrew...")
    # Assuming your crew.py is in Backend/app/crew.py
    from app.crew import ImageAnalysisCrew 
    print("ImageAnalysisCrew imported successfully.")

    print("Attempting to instantiate ImageAnalysisCrew...")
    # Ensure your .env file with REDIS_URL and GROQ_API_KEY is accessible
    # from where you run this script, or that the variables are set in your environment.
    # The load_dotenv() in crew.py should handle it if .env is in Backend/.
    crew_instance = ImageAnalysisCrew()
    print("ImageAnalysisCrew instantiated successfully.")
    print("If you got here, the basic crew initialization (including tools) seems to be working without CRITICAL errors.")
    
    # You could potentially call crew_instance.run({}) here if you want to test further,
    # but for the 'SessionRetrievalTool' error, just instantiation is key.

except ModuleNotFoundError as e:
    print(f"ERROR - ModuleNotFoundError: {e}")
    print("This usually means Python cannot find the 'app' module or one of its submodules.")
    print("Ensure you are running this script from the 'Backend' directory,")
    print("and that your PYTHONPATH is set up correctly if needed.")
    print("Current sys.path:", sys.path)
    traceback.print_exc()
except ValueError as e:
    print(f"ERROR - ValueError during crew initialization: {e}")
    print("This might be related to missing environment variables (e.g., REDIS_URL, GROQ_API_KEY) or configuration issues.")
    traceback.print_exc()
except Exception as e:
    print(f"ERROR - An unexpected error occurred during crew initialization: {e}")
    print("Full traceback:")
    traceback.print_exc()
