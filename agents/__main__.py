# !/bin/python3

# KaliGPT v1.3 (HackerX)
# /agents/__main__.py
# Set AI API keys & launch default model agent, provide Configuration (reset model, change model etc.) management
# Last Modified: 2 feb 2026

import sys
import subprocess
from .utils.agent_configs import ENV_VAR_MAP, get_available_ais, get_default_provider
from .utils.agent_management import AI_MANAGEMENT_OPTIONS, agent_management

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# --- Set API key ---
def set_api_keys():
    try:
        print("KaliGPT now reads API keys from environment variables only.\n")
        for ai in get_available_ais():
            env_var = ENV_VAR_MAP.get(ai, "?")
            print(f"  {ai}: set {env_var}")

        print("\nTo set a key permanently, add to your shell profile:")
        print("  PowerShell:  [System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY','your-key','User')")
        print("  bash/zsh:    export GEMINI_API_KEY='your-key'  (add to ~/.bashrc)")

    except KeyboardInterrupt:
        print("\nSee You,\nExiting Setup - KeyBoardInterrupt")


def main(args):

    match args:
        case ["--setup-keys"]:
            set_api_keys()

        case [option] if option in AI_MANAGEMENT_OPTIONS[:4]:
            agent_management(option)

        case _:
            default_model = get_default_provider()
            prompt: str = "Are you Ready for Hacking?"
            if len(args) > 0 and args[0].strip():
                prompt = args[0]

            command = ["python", "-m", f"agents.{default_model}", prompt]
            # print(f"[+] Launching KaliGPT with default model: {default_model} & prompt: {prompt}")
            
            try:
                # using python -m agents.agent_module_name to launch the agent
                # print(f"Running command: {' '.join(command)}")
                subprocess.run(command)

            except Exception as e:
                print(f"Exception occurred: {e}")

            except KeyboardInterrupt:
                print("\n\n")   # MSG already printed by running agent module

if __name__ == "__main__":
    # print(sys.argv[1:])
    main(sys.argv[1:])
