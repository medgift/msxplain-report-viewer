

def parse_transform_params(filename):
        with open(filename, 'r') as f:
            lines = f.readlines()
            for line in lines:
                if 'TransformParameters' in line:
                    print(line)
                    params = [float(x) for x in line.split('(TransformParameters ')[1].strip(')\n').split()]
                    rotation_angles = params[0:3]
                    translation = params[3:6]
                    print(rotation_angles)
                    print(translation)
                elif 'CenterOfRotationPoint' in line:
                    print(line)
                    center_of_rotation = [float(x) for x in line.split('(CenterOfRotationPoint ')[1].strip(')\n').split()]
                    print(center_of_rotation)
        
        return rotation_angles, translation, center_of_rotation