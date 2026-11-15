"""Compatibility entry; use python -m scripts.index_algorithms."""
if __package__:
    from .index_algorithms import main
else:
    from index_algorithms import main

if __name__=='__main__':
    main()
