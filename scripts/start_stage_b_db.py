"""Compatibility entry; use python -m scripts.start_database for new operations."""
if __package__:
    from .start_database import main
else:
    from start_database import main

if __name__ == '__main__':
    main()
