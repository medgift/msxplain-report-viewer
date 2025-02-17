import subprocess
import traceback

def run_command(command):
    """Run a shell command and handle errors"""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Command failed: {stderr}")
            
        return stdout
    except Exception as e:
        print(f"Error running command {' '.join(command)}: {str(e)}")
        traceback.print_exc()
        raise