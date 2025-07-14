from typing import Optional
import re

def get_user_input(prompt: str) -> str:
    """
    Get user input from command line with proper handling.
    
    Args:
        prompt: The prompt to display to the user
        
    Returns:
        str: The user's input, stripped of whitespace
    """
    try:
        user_input = input(prompt).strip()
        return user_input
    except (EOFError, KeyboardInterrupt):
        print("\nOperation cancelled by user.")
        return "q"

def validate_source_name(name: str) -> bool:
    """
    Validate a source name.
    
    Args:
        name: The source name to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not name:
        print("Error: Source name cannot be empty")
        return False
    
    if len(name) < 2:
        print("Error: Source name must be at least 2 characters long")
        return False
    
    if len(name) > 100:
        print("Error: Source name must be less than 100 characters")
        return False
    
    # Check for invalid characters
    if re.search(r'[<>:"/\\|?*]', name):
        print("Error: Source name contains invalid characters")
        return False
    
    return True

def confirm_source_details(source_url: str, source_name: str) -> bool:
    """
    Show source details and ask for confirmation.
    
    Args:
        source_url: The source URL
        source_name: The source name
        
    Returns:
        bool: True if confirmed, False otherwise
    """
    print("\n" + "="*50)
    print("SOURCE DETAILS CONFIRMATION")
    print("="*50)
    print(f"URL: {source_url}")
    print(f"Name: {source_name}")
    print("="*50)
    
    while True:
        response = get_user_input("\nDo these details look correct? (y/n/q): ").lower()
        
        if response == "q":
            print("Operation cancelled.")
            return False
        elif response == "y":
            return True
        elif response == "n":
            return False
        else:
            print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")

def get_source_name_with_retry() -> Optional[str]:
    """
    Get source name from user with retry option.
    
    Returns:
        Optional[str]: The source name if provided, None if cancelled
    """
    while True:
        source_name = get_user_input("\nEnter source name: ").strip()
        
        if source_name.lower() == "q":
            print("Operation cancelled.")
            return None
        
        if validate_source_name(source_name):
            return source_name
        
        # Ask if they want to try again
        retry = get_user_input("Would you like to try again? (y/n/q): ").lower()
        if retry == "q":
            print("Operation cancelled.")
            return None
        elif retry != "y":
            print("Operation cancelled.")
            return None

def prompt_for_source_addition(source_url: str) -> Optional[str]:
    """
    Complete workflow for prompting user to add source to database.
    
    Args:
        source_url: The URL that was successfully scraped
        
    Returns:
        Optional[str]: The source name if user wants to add to DB, None otherwise
    """
    print(f"\nArticle extracted successfully from: {source_url}")
    
    # First prompt: Do you want to add this source to the database?
    while True:
        response = get_user_input("\nWould you like to add this source to the database? (y/n/q): ").lower()
        
        if response == "q":
            print("Operation cancelled.")
            return None
        elif response == "n":
            print("Source not added to database.")
            return None
        elif response == "y":
            break
        else:
            print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
    
    # Get source name
    source_name = get_source_name_with_retry()
    if not source_name:
        return None
    
    # Confirm details
    if not confirm_source_details(source_url, source_name):
        # Give them another chance to enter the name
        print("\nLet's try entering the source name again.")
        source_name = get_source_name_with_retry()
        if not source_name:
            return None
        
        # Final confirmation
        if not confirm_source_details(source_url, source_name):
            print("Operation cancelled.")
            return None
    
    return source_name
