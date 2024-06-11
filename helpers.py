import argparse
import os
import re
import sys


class Segment:
    def __init__(self, point_a, point_b):
        if point_a < point_b:
            self.point_a, self.point_b = point_a, point_b
        else:
            self.point_a, self.point_b = point_b, point_a

    def __hash__(self):
        return hash((self.point_a, self.point_b))

    def __eq__(self, other):
        return (self.point_a, self.point_b) == (other.point_a, other.point_b)

    def __repr__(self):
        return f"Segment({repr(self.point_a)}, {repr(self.point_b)})"
    
    def __iter__(self):
        # Allows unpacking the segment into its endpoints
        return iter((self.point_a, self.point_b))

    def is_point_on_segment(self, point_c, tolerance):
        # Vector from A to B and A to C
        vector_ab = self.point_b - self.point_a
        vector_ac = point_c - self.point_a

        # Check if AC is a scalar multiple of AB and the point lies between A and B
        cross_product = vector_ab.cross(vector_ac)
        dot_product = vector_ab.dot(vector_ac)

        return abs(cross_product.magnitude) <= tolerance and 0 <= dot_product <= vector_ab.dot(vector_ab)

    def length(self):
        return (self.point_b - self.point_a).magnitude

    def midpoint(self):
        return self.point_a + (self.point_b - self.point_a) * 0.5

    def is_parallel_to(self, other):
        # Cross product of AB vectors of both segments, should be zero if parallel
        return (self.point_b - self.point_a).cross(other.point_b - other.point_a).magnitude == 0

    def is_perpendicular_to(self, other):
        # Dot product of AB vectors of both segments, should be zero if perpendicular
        return (self.point_b - self.point_a).dot(other.point_b - other.point_a) == 0

def extract_value(input_string):
    # Define the regular expression pattern
    pattern = r'^([\d\s,\.]+)(.*)$'
    
    # Match the pattern
    match = re.match(pattern, input_string)
    
    if match:
        value = match.group(1)
        units = match.group(2)
        
        # Remove spaces and commas from the first part
        value = value.replace(' ', '').replace(',', '')
        
        # Convert first part to float
        if value:
            value = float(value)
        else:
            value = 0.0
        return value, units
    
    else:
        return None, None


def extract_parameters(input_string):
    # Split the text into lines
    lines = input_string.replace(':', '').replace('=', '').split('\P')
    
    # Initialize the result dictionary
    result = {'E': None, 'A': None, 'I': None}
    
    for line in lines:
        line = line.strip()
        if line[0] in result:
            # Apply parse_string function
            value, units = extract_value(line[1:])
            result[line[0]] = value
        else:
            raise ValueError
    
    for value in result.values():
        if not value:
            raise ValueError
    
    return result


def valid_layer_name(layer_name):
    if not layer_name:
        raise argparse.ArgumentTypeError("Layer name cannot be empty.")

    if not re.match(r'^[a-zA-Z0-9_-]+$', layer_name):
        raise argparse.ArgumentTypeError(f"Layer name {layer_name} has incorrect characters.")
    
    if len(layer_name) > 255:
        raise argparse.ArgumentTypeError(f"Layer name {layer_name} has incorrect length.")
    
    return layer_name


def valid_input_file_path(path):
    path = path.strip()
    
    # Check if the path exists
    if not os.path.exists(path):
        raise argparse.ArgumentTypeError(f"The file {path} does not exist.")
    
    # Check if the path is indeed a file (and not a directory, for instance)
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f"{path} is not a file.")
    
    # Check for .dxf extension
    _, ext = os.path.splitext(path)
    if ext.lower() != '.dxf':
        raise argparse.ArgumentTypeError(f"{path} is not a .dxf file.")

    return path


def valid_output_file_path(path):
    path = path.strip()

    if not path:
        raise argparse.ArgumentTypeError("Output path name cannot be empty.")
    
    # Get the directory name or use the current directory if it's empty
    directory = os.path.dirname(path) or '.'

    # Check if the directory is writable
    if not os.access(directory, os.W_OK):
        raise argparse.ArgumentTypeError(f"Invalid path: {path}")

    # Check for .dxf extension
    _, ext = os.path.splitext(path)
    if ext.lower() != '.dxf':
        raise argparse.ArgumentTypeError(f"{path} is not a .dxf file.")
    
    return path


def get_cli_args():
    parser = argparse.ArgumentParser(description="Process a DXF file for structural analysis.")
    
    # Mandatory arguments
    parser.add_argument("input_path", type=valid_input_file_path, help="Path to the input DXF file.")
    parser.add_argument("analysis_layer", type=valid_layer_name, help="Name of the layer to analyze.")
    
    # Printing
    parser.add_argument('-p', '--print', action='append', choices=[
        'all_results',
        'structure',
        'reaction_force',
        'axial_force',
        'shear_force',
        'bending_moment',
        'displacement'
        ], help="Specify what should be printed.")
    
    # Displacements drawing
    parser.add_argument("-o", "--output_path", type=valid_output_file_path, help="Output name of the DXF file with displacements. Defaults to rewriting the existing file.")
    parser.add_argument("-l", "--output_layer", type=valid_layer_name, help="Output name of the layer with displacements. Defaults to adding to the existing layer.")
    parser.add_argument("-t", "--displacement_type", type=str, choices=['points', 'lines'], default='lines', help="Specify if displacements should be drawn as points or lines.")
    parser.add_argument("-c", "--displacement_color", metavar='[0-255]', type=int, choices=range(256), default=256, help="Color of the displacements to be drawn (0-255). Defaults to be drawn ByLayer")

    return parser.parse_args()