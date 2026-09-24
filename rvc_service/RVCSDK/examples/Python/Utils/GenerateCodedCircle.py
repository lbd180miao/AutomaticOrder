import cairo
import math
import os

def draw_annular_sector(context, x, y, inner_radius, outer_radius, start_angle, end_angle, color):
    context.set_source_rgb(*color)
    context.new_sub_path()
    context.arc(x, y, outer_radius, start_angle, end_angle)
    context.line_to(x + inner_radius * math.cos(end_angle), y + inner_radius * math.sin(end_angle))
    context.arc_negative(x, y, inner_radius, end_angle, start_angle)
    context.close_path()
    context.fill()

def calculate_degrees(code):
    n = len(code)
    degree_per_position = 2 * math.pi / n 
    result = []
    i = 0

    while i < n:
        if code[i] == '1':
            start = i
            while i < n and code[i] == '1':
                i += 1
            end = i
            result.append((start * degree_per_position, end * degree_per_position))
        else:
            i += 1

    return result

import itertools
import math

def smallest_cyclic_binary(binary_str):
    min_binary = binary_str
    for i in range(len(binary_str)):
        shifted_str = binary_str[i:] + binary_str[:i]
        if shifted_str < min_binary:
            min_binary = shifted_str
    return min_binary

def generate_minimal_cyclic_permutations(n):
    all_permutations = set()
    for perm in itertools.product('01', repeat=n):
        binary_str = ''.join(perm)
        min_binary = smallest_cyclic_binary(binary_str)
        all_permutations.add(min_binary)

    return sorted(all_permutations)

def binary_to_decimal(binary_str):
    return int(binary_str, 2)

def generate_minimal_cyclic_permutations_decimal(n):
    minimal_binaries = generate_minimal_cyclic_permutations(n)
    decimal_list = [binary_to_decimal(bin_str) for bin_str in minimal_binaries]
    codes_decimal = sorted(decimal_list)
    codes_decimal = codes_decimal[1:-1]
    return codes_decimal

def decimal_to_binary_fixed_length(decimal_number, length):
    binary_str = bin(decimal_number)[2:]
    padding = '0' * (length - len(binary_str))
    return padding + binary_str

def decimal_list_to_binary_fixed_length(decimal_list, length):
    return [decimal_to_binary_fixed_length(number, length) for number in decimal_list]

def draw_single_decoded_circle(surface, decimal_code, binary_code, x, y, radius, r1_to_r0_ratio, r2_to_r0_ratio, r3_to_r0_ratio, r4_to_r0_ratio):
    degrees = calculate_degrees(binary_code)

    context.set_source_rgb(0, 0, 0)
    context.rectangle(x - radius * r3_to_r0_ratio, y - radius * r3_to_r0_ratio, 2 * radius * r3_to_r0_ratio, 2*radius * r3_to_r0_ratio)
    context.fill()

    context.set_source_rgb(1, 1, 1)
    context.arc(x, y, radius, 0, 2 * math.pi)
    context.fill()

    for start_angle, end_angle in degrees:
        draw_annular_sector(context, x, y, radius * r1_to_r0_ratio, radius * r2_to_r0_ratio, start_angle, end_angle, (1, 1, 1))

    font_size = radius * (r4_to_r0_ratio - r3_to_r0_ratio)
    context.set_source_rgb(0, 0, 0)
    context.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    context.set_font_size(font_size)
    context.move_to(x - font_size, y + radius * r4_to_r0_ratio)
    context.show_text(str(decimal_code))
    
# parameters
n = 8
page_type = 'A4'
r1_to_r0_ratio = 2.0
r2_to_r0_ratio = 3.0
r3_to_r0_ratio = 4.0
r4_to_r0_ratio = 5.0
radius = 6 # center circle radius, unit: mm

codes_decimal = generate_minimal_cyclic_permutations_decimal(n)
print("Total nums: " + str(len(codes_decimal)))
codes_binary = decimal_list_to_binary_fixed_length(codes_decimal, n)
width, height = 0, 0
if page_type == 'A1':
    width, height = int(59.4 * 300 / 2.54), int(84.1 * 300 / 2.54)
elif page_type == 'A2':
    width, height = int(42 * 300 / 2.54), int(59.4 * 300 / 2.54)
elif page_type == 'A3':
    width, height = int(29.7 * 300 / 2.54), int(42 * 300 / 2.54)
elif page_type == 'A4':
    width, height = int(21 * 300 / 2.54), int(29.7 * 300 / 2.54)
elif page_type == 'A5':
    width, height = int(14.8 * 300 / 2.54), int(21 * 300 / 2.54)
elif page_type == 'A6':
    width, height = int(10.5 * 300 / 2.54), int(14.8 * 300 / 2.54)

radius = radius * 0.1 * 300 / 2.54
x, y = width/2, height/2

nums_per_width = int(width // (2 * radius * r4_to_r0_ratio))
nums_per_height = int(height // (2 * radius * r4_to_r0_ratio))

if not os.path.exists('OutputCodedCircleData'):
    os.makedirs('OutputCodedCircleData')

current_index = 0
has_finished = False
page_index = 0
max_page_index = 100
while not has_finished:
    surface = cairo.PDFSurface(f'OutputCodedCircleData/{page_index}.pdf', width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(1, 1, 1) 
    context.paint()
    for i in range(nums_per_height):
        for j in range(nums_per_width):
            x = radius * r4_to_r0_ratio + 2 * j * radius * r4_to_r0_ratio
            y = radius * r4_to_r0_ratio + 2 * i * radius * r4_to_r0_ratio
            if current_index >= len(codes_decimal):
                current_index = 0
                has_finished = True
                break
            draw_single_decoded_circle(surface, codes_decimal[current_index], codes_binary[current_index], x, y, radius, r1_to_r0_ratio, r2_to_r0_ratio, r3_to_r0_ratio, r4_to_r0_ratio)
            current_index += 1
    surface.finish()
    page_index += 1
    if page_index >= max_page_index:
        break


