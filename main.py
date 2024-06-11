import collections
import sys
import ezdxf
from ezdxf.acc.vector import Vec3
from anastruct import SystemElements, basic

from helpers import extract_value, extract_parameters, get_cli_args, Segment


TOLERANCE = 1e-6

Element = collections.namedtuple('Element', ('color'))
Support = collections.namedtuple('Support', ('rotation'))
Force = collections.namedtuple('Force', ('value', 'rotation'))
Q_force = collections.namedtuple('Q_force', ('value', 'rotation'))
Moment = collections.namedtuple('Moment', ('value'))
Material = collections.namedtuple('Material', ('EA', 'EI'))


def load_data(path, layer_name):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    elements = dict()
    supports = collections.defaultdict(dict)
    loads = collections.defaultdict(dict)
    materials = dict()
    vectors_map = dict()

    def are_points_close(vertex_a, vertex_b, tolerance):
        # Calculate the vector representing the difference between the points
        diff_vector = vertex_b - vertex_a

        # Calculate the distance between the points
        distance = diff_vector.magnitude

        # Check if the distance is within the tolerance
        return distance <= tolerance
    
    def check_point(vector):
        for vector_from_map in vectors_map:
            if are_points_close(vector, vector_from_map, TOLERANCE):
                return vector_from_map
        vectors_map[vector] = None
        return vector
    
    def add_intermediate_point(vector, dict_to_update):
        segment_found = None
        for segment in dict_to_update:
            start, end = segment
            if segment.is_point_on_segment(vector, TOLERANCE) and vector not in (start, end):
                segment_found = segment
                break

        if segment_found:
            element_props = dict_to_update[segment_found]
            new_segments = {
                Segment(start, vector): element_props,
                Segment(vector, end): element_props
            }
            del dict_to_update[segment_found]
            dict_to_update.update(new_segments)

    for entity in msp:
        if entity.dxf.layer == layer_name:

            # adding elements
            if entity.dxftype() == 'LINE':
                start = check_point(entity.dxf.start)
                end = check_point(entity.dxf.end)
                elements[Segment(start, end)] = Element(entity.dxf.color)
            elif entity.dxftype() == 'LWPOLYLINE':
                vertices = []
                for x, y, z, *_ in entity:
                    vertices.append(check_point(Vec3(x,y,z)))
                if entity.is_closed:
                    vertices.append(vertices[0])

                for start, end in zip(vertices[:-1], vertices[1:]):
                    elements[Segment(start, end)] = Element(entity.dxf.color)

            elif entity.dxftype() == 'INSERT':  # Check if it's a block reference
                # adding supports
                if entity.dxf.name in ['support_fixed', 'support_hinged', 'support_roll']:
                    supports[entity.dxf.name][check_point(entity.dxf.insert)] = Support(entity.dxf.rotation)

                elif entity.dxf.name == 'material':
                    p = dict()
                    for attrib in entity.attribs:
                        tag = attrib.dxf.tag
                        try:
                            value, unit = extract_value(attrib.dxf.text)
                        except ValueError:
                            sys.exit('Check material assignment')
                        p[tag] = value
                    materials[entity.dxf.color] = Material(p['E'] * p['A'], p['E'] * p['I'])
                
                # adding loads
                elif entity.attribs:
                    for attrib in entity.attribs:
                        tag = attrib.dxf.tag
                        try:
                            value, unit = extract_value(attrib.dxf.text)
                        except ValueError:
                            sys.exit('Check loads assignment')
                        
                        # force case
                        if tag == 'force':
                            for virtual_entity in entity.virtual_entities():  # Get the virtual entities
                                if virtual_entity.dxftype() == 'INSERT' and virtual_entity.dxf.name == 'Arrow':
                                    loads[tag][check_point(virtual_entity.dxf.insert)] = Force(value, -virtual_entity.dxf.rotation)

                        # q-force case
                        elif tag == 'q-force':
                            start, end, rotation = (), (), float()
                            for virtual_entity in entity.virtual_entities():  # Get the virtual entities
                                if virtual_entity.dxftype() == 'INSERT' and virtual_entity.dxf.name == 'Arrow':
                                    rotation = virtual_entity.dxf.rotation
                                elif virtual_entity.dxftype() == 'LINE' and virtual_entity.dxf.layer.lower() == 'defpoints':
                                    start = check_point(virtual_entity.dxf.start)
                                    end = check_point(virtual_entity.dxf.end)
                            loads[tag][Segment(start, end)] = Q_force(value, rotation)
                        
                        # moment case
                        elif tag == 'moment':
                            for virtual_entity in entity.virtual_entities():  # Get the virtual entities
                                if virtual_entity.dxftype() == 'INSERT' and virtual_entity.dxf.name == 'Arrowhead':
                                    sign = 2 * (virtual_entity.dxf.xscale >= 0) - 1
                            loads[tag][check_point(entity.dxf.insert)] = Moment(sign * value)
            
            # adding materials
            elif entity.dxftype() == 'MTEXT':
                try:
                    p = extract_parameters(entity.text)
                except ValueError:
                    sys.exit('Check material assignment')
                materials[entity.dxf.color] = Material(p['E'] * p['A'], p['E'] * p['I'])


    # add addintional vertices
    for vector in vectors_map:
        add_intermediate_point(vector, elements)
        add_intermediate_point(vector, loads['q-force'])
                
    return elements, supports, loads, materials, vectors_map
     

def compile_model(elements, supports, loads, materials, vectors_map):
    ss = SystemElements()

    # create elements
    node_id_counter = 1
    elemens_vector_map = {}
    for segment in elements:
        start, end = segment
        x1, y1, z1 = start
        x2, y2, z2 = end
        if z1 or z2:
            print(f'WARNING!\nSegment {segment} is not flat.\n(has coodinate z)')

        if elements[segment].color not in materials:
            print(f'WARNING!\nElement material for {elements[segment].color} color is not defined.\nDefault material had been assigned. EA=15000, EI=5000')
            materials[elements[segment].color] = Material(None, None)
        EA = materials[elements[segment].color].EA
        EI = materials[elements[segment].color].EI
        
        element_id = ss.add_element(location=[(x1,y1), (x2,y2)], EA=EA, EI=EI)

        elemens_vector_map[segment] = element_id
        if not vectors_map[start]:
            vectors_map[start] = node_id_counter
            node_id_counter += 1
        if not vectors_map[end]:
            vectors_map[end] = node_id_counter
            node_id_counter += 1

    # apply supports
    for support_type in supports:
        for vector in supports[support_type]:
            if vectors_map[vector]:
                if support_type == 'support_fixed':
                    ss.add_support_fixed(node_id=vectors_map[vector])
                elif support_type == 'support_hinged':
                    ss.add_support_hinged(node_id=vectors_map[vector])
                else: # support_type == 'support_roll':
                    ss.add_support_roll(node_id=vectors_map[vector], angle=supports[support_type][vector].rotation)
    
    # apply loads
    for load_type in loads:
        for vector in loads[load_type]:
            load = loads[load_type][vector]
            if load_type == 'force':
                if vectors_map[vector]:
                    ss.point_load(node_id=vectors_map[vector], Fx=load.value, rotation=load.rotation)
            elif load_type == 'q-force':
                if elemens_vector_map[vector]:
                    ss.q_load(element_id=elemens_vector_map[vector], q=load.value, rotation=load.rotation)
            else: # load_type == 'moment':
                if vectors_map[vector]:
                    ss.moment_load(node_id=vectors_map[vector], Ty=load.value)
    
    try:
        ss.solve()
    except basic.FEMException:
        print("Structure is not statically defined. Check all elements")
        sys.exit(11)
    return ss


def draw_displacements(ss, args):

    # Load an existing DXF document
    doc = ezdxf.readfile(args.input_path)
    msp = doc.modelspace()

    if not args.output_path:
        args.output_path = args.input_path

    if not args.output_layer:
        args.output_layer = args.analysis_layer

    if args.displacement_type == "lines":
        if 'DASHED' not in doc.linetypes:
            doc.linetypes.new('DASHED')

    for node in ss.node_map.values():
        start = (node.vertex.x, node.vertex.y)
        end = (node.vertex.x - node.ux, node.vertex.y + node.uy)
        if start != end:
            if args.displacement_type == "lines":
                line = msp.add_line(start, end)
                line.dxf.linetype = 'DASHED'
                line.dxf.layer = args.output_layer
                line.dxf.color = args.displacement_color
            else: # args.displacement_type == "points":
                point = msp.add_point(end)
                # Setting properties
                point.dxf.layer = args.output_layer  # the layer of the displaced points
                point.dxf.color = args.displacement_color  # Set the color of the point

    # Save the changes in the existing file
    doc.saveas(args.output_path)


def main():
    args = get_cli_args()

    data = load_data(args.input_path, args.analysis_layer)

    model = compile_model(*data)

    if args.print:
        # Mapping of choices to functions
        functions = {
            'all_results': model.show_results,
            'structure': model.show_structure,
            'reaction_force': model.show_reaction_force,
            'axial_force': model.show_axial_force,
            'shear_force': model.show_shear_force,
            'bending_moment': model.show_bending_moment,
            'displacement': model.show_displacement,
        }

        for item in args.print:
            if item in functions:
                functions[item]()

    if args.output_path or args.output_layer:
        draw_displacements(model, args)


if __name__ == '__main__':
    main()