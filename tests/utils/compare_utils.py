import numpy as np
import mitsuba as mi

def mae(img1: np.ndarray, img2: np.ndarray, gray_scale=True):
    '''
    Compute and return error and variance between image img1 and image img2 using mean absolute error
    
    ## Paramters

    img1 : ndarray
        First image to compare represented as rgba numpy array
    img2 : ndarray
        Second image to compare represented as rgba numpy array

    ## Return

    mae : float
        Average of absolute difference between pixels in img1 and img2 
    std_dev : float
        The standard deviation of the absolute difference between pixels img1 and img2
    diff_img: np.ndarray
        Gray scale image of the absolute difference between pixels in img1 and img2  
    '''
    assert img1.shape[2] == 3 and img2.shape[2] == 3, f"""Image 1 or 2 is not in RGB format. 
    Image 1 uses {img1.shape[2]} channels and image 2 uses {img2.shape[2]}"""
    assert img1.shape == img2.shape, f"Image 1 has shape {img1.shape} and image 2 has shape {img2.shape}"

    # Compute absolute error and difference image
    abs_err = np.abs(img1 - img2)

    # Compute error and variance
    pixels = img1.shape[0] * img2.shape[1]
    mae = abs_err.sum() / pixels
    std_dev = ((abs_err.sum(axis=-1) - mae) ** 2).sum() / pixels

    # Compute gray scale image of differences
    if gray_scale:
        diff_img = to_gray_scale(abs_err)
    else:
        diff_img = None
    
    return mae, std_dev, diff_img

def mse(img1: np.ndarray, img2: np.ndarray, gray_scale=True):
    '''
    Compute and return error and variance between image img1 and image img2 using mean square error
    
    ## Paramters

    img1 : ndarray
        First image to compare represented as rgba numpy array
    img2 : ndarray
        Second image to compare represented as rgba numpy array

    ## Return

    mse : float
        Average of square error between pixels in img1 and img2 
    std_dev : float
        The standard deviation of the absolute difference between pixels img1 and img2
    diff_img: np.ndarray
        Gray scale image of the square error between pixels in img1 and img2  
    '''
    assert img1.shape[2] == 3 and img2.shape[2] == 3, f"""Image 1 or 2 is not in RGB format. 
    Image 1 uses {img1.shape[2]} channels and Image 2 uses {img2.shape[2]}"""
    assert img1.shape == img2.shape, f"image 1 has shape {img1.shape} and image 2 has shape {img2.shape}"

    # Compute absolute error and difference image
    s_err = ((img1 - img2) ** 2)

    # Compute error and variance
    pixels = img1.shape[0] * img2.shape[1]
    mse = s_err.sum() / pixels
    std_dev = ((s_err.sum(axis=-1) - mse) ** 2).sum() / pixels

    # Compute gray scale image of differences
    if gray_scale:
        diff_img = to_gray_scale(s_err)
    else:
        diff_img = None

    return mse, std_dev, diff_img

def convert_png(bmp):
    return bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, True)

def to_gray_scale(img: np.ndarray):
    assert img.shape[2] == 3, f"Image has {img.shape[2]} pixel channels instead of 3"
    return np.dot(img, [0.2126, 0.7152, 0.0722])