

def transform_registration_params(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
        for line in lines:
            # Look specifically for the line that starts with (TransformParameters
            if line.strip().startswith('(TransformParameters '):
                params = [float(x) for x in line.split('(TransformParameters ')[1].strip(')\n').split()]
                rotation_angles = params[0:3]
                translation = params[3:6]

            elif 'CenterOfRotationPoint' in line:
                center_of_rotation = [float(x) for x in line.split('(CenterOfRotationPoint ')[1].strip(')\n').split()]
    
    return rotation_angles, translation, center_of_rotation
