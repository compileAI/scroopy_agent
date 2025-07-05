"""
Interactive CLI for Scroopy Agent
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("⚠️ python-dotenv not installed - environment variables may not be loaded")

from .session import SimpleSession
from .commands import COMMANDS
from .display import display_error


class InteractiveCLI:
    """Interactive CLI for Scroopy Agent"""
    
    def __init__(self):
        self.session = SimpleSession()
        
    async def run(self):
        """Main interactive loop"""
        print("🤖 Scroopy Interactive CLI v1.0")
        print("Type 'help' for available commands or 'exit' to quit.\n")
        
        try:
            while True:
                try:
                    # Show prompt with context
                    prompt = self._get_prompt()
                    user_input = input(prompt).strip()
                    
                    if not user_input:
                        continue
                        
                    # Parse command
                    parts = self._parse_input(user_input)
                    if not parts:
                        continue
                        
                    command = parts[0].lower()
                    args = parts[1:]
                    
                    # Execute command
                    should_exit = await self._execute_command(command, args)
                    if should_exit:
                        break
                        
                except KeyboardInterrupt:
                    print("\n👋 Goodbye!")
                    break
                except EOFError:
                    print("\n👋 Goodbye!")
                    break
                except Exception as e:
                    display_error(f"Unexpected error: {str(e)}")
        finally:
            # Clean up resources
            await self._cleanup()
    
    async def _cleanup(self):
        """Clean up resources before exit"""
        try:
            # Close the shared crawler if it exists
            from utils.crawler_manager import close_crawler
            await close_crawler()
        except Exception as e:
            # Don't show errors during cleanup
            pass
                
    def _get_prompt(self) -> str:
        """Get the current prompt string"""
        if self.session.has_current_url():
            domain = self.session.get_domain()
            return f"scroopy [{domain}]> "
        else:
            return "scroopy> "
    
    def _parse_input(self, user_input: str) -> list:
        """Parse user input into command and arguments"""
        # Handle quoted arguments (for improve command, etc.)
        parts = []
        current_part = ""
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(user_input):
            char = user_input[i]
            
            if char in ['"', "'"] and not in_quotes:
                # Start of quoted string
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                # End of quoted string
                in_quotes = False
                quote_char = None
            elif char == ' ' and not in_quotes:
                # Space outside quotes - end current part
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                # Regular character
                current_part += char
            
            i += 1
        
        # Add the last part
        if current_part:
            parts.append(current_part)
        
        return parts
    
    async def _execute_command(self, command: str, args: list) -> bool:
        """Execute a command and return True if should exit"""
        if command not in COMMANDS:
            available_commands = self._get_available_commands()
            display_error(f"Unknown command: {command}")
            print(f"Available commands: {', '.join(available_commands)}")
            print("Type 'help' for more information.")
            return False
        
        try:
            result = await COMMANDS[command](self.session, args)
            return result is True  # Exit command returns True
        except Exception as e:
            display_error(f"Command failed: {str(e)}")
            return False
    
    def _get_available_commands(self) -> list:
        """Get list of available commands based on current state"""
        # Always available
        always_available = ["help", "exit", "reset"]
        
        # State-dependent commands
        if not self.session.has_current_url():
            return always_available + ["discover", "use"]
        elif not self.session.has_link_schema():
            return always_available + ["link-schema"]
        elif not self.session.has_sample_urls():
            return always_available + ["test-links", "sample", "add-article"]
        elif not self.session.has_article_schema():
            return always_available + ["article-schema", "list-articles", "add-article", "remove-article", "clear-articles"]
        else:
            return always_available + ["test-schema", "test-schema-all", "test-article", "critique", "improve", "validate", "list-articles", "add-article", "remove-article", "clear-articles", "save"]


def main():
    """Entry point for the interactive CLI"""
    # Set up basic logging to reduce noise
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Check environment setup
    import os
    required_vars = ["GOOGLE_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"⚠️ Warning: Missing environment variables: {', '.join(missing_vars)}")
        print("Some features may not work properly.")
        print()
    
    # Run the CLI
    try:
        cli = InteractiveCLI()
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to start CLI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 