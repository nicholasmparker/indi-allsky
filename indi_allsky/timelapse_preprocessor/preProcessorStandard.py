from pathlib import Path
import tempfile
import io
import logging
import cv2
import simplejpeg
import PIL
from PIL import Image
import numpy

from .preProcessorBase import PreProcessorBase


logger = logging.getLogger('indi_allsky')


class PreProcessorStandard(PreProcessorBase):

    def __init__(self, *args, **kwargs):
        super(PreProcessorStandard, self).__init__(*args, **kwargs)


        # this needs to be a class variable
        # tmp folder needs to be in /tmp so symlinks are supported (image_dir might be fat32)
        self.temp_seqfolder_path = tempfile.mkdtemp(suffix='_timelapse')
        self._seqfolder = Path(self.temp_seqfolder_path)


    def main(self, file_list):
        # Calculate target dimensions from first image to ensure all frames have same size
        target_width = None
        target_height = None

        if self.pre_scale < 100 and len(file_list) > 0:
            # Read first image to determine target dimensions
            first_img = self._read_image(file_list[0])
            if first_img is not None:
                image_height, image_width = first_img.shape[:2]
                target_height = int(image_height * (self.pre_scale / 100))
                target_width = int(image_width * (self.pre_scale / 100))

                # Ensure dimensions are even (required for video encoding)
                if target_height % 2 != 0:
                    target_height -= 1
                if target_width % 2 != 0:
                    target_width -= 1

                logger.info('Target dimensions for all frames: %dx%d', target_width, target_height)

        for i, f in enumerate(file_list):
            # the symlink files must start at index 0 or ffmpeg will fail

            # If pre_scale is set and < 100, scale the images for VAAPI compatibility
            if self.pre_scale < 100:
                self._process_scaled_image(i, f, target_width, target_height)
            else:
                # Just create symlinks (original behavior)
                p_symlink = self.seqfolder.joinpath('{0:05d}.{1:s}'.format(i, self.config['IMAGE_FILE_TYPE']))
                p_symlink.symlink_to(f)


    def _read_image(self, f):
        """Read an image file and return as numpy array"""
        if f.suffix in ('.jpg', '.jpeg'):
            try:
                with io.open(str(f), 'rb') as f_img:
                    return simplejpeg.decode_jpeg(f_img.read(), colorspace='BGR')
            except ValueError as e:
                logger.error('Unable to read - %s: %s', str(e), f)
                return None
        elif f.suffix in ('.png',):
            image = cv2.imread(str(f), cv2.IMREAD_COLOR)
            if isinstance(image, type(None)):
                logger.error('Unable to read %s', f)
                return None
            return image
        else:
            # Pillow supports remaining image types
            try:
                with Image.open(str(f)) as img_pil:
                    return cv2.cvtColor(numpy.array(img_pil), cv2.COLOR_RGB2BGR)
            except PIL.UnidentifiedImageError:
                logger.error('Unable to read %s', f)
                return None


    def _process_scaled_image(self, i, f, target_width, target_height):
        """Read, scale, and save image for VAAPI hardware encoding compatibility"""
        # Read the image
        image = self._read_image(f)
        if image is None:
            return

        # Scale the image to target dimensions (same for all frames)
        scaled_image = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)

        # Save scaled image
        # Use cv2.imwrite for JPEG to ensure yuv420p pixel format (VAAPI compatible)
        # simplejpeg creates yuvj444p which triggers FFmpeg auto-scaler issues
        output_file = self.seqfolder.joinpath('{0:05d}.{1:s}'.format(i, self.config['IMAGE_FILE_TYPE']))
        cv2.imwrite(str(output_file), scaled_image, [cv2.IMWRITE_JPEG_QUALITY, 95])

