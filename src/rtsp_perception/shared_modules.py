# We can heavily reuse the detection and publisher logic from the edge vision agent.
# Using relative imports or updating sys.path for the MVP.
import sys
import os

# Add edge_vision to path so we can import its modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'edge_vision')))

