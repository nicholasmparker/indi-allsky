#!/usr/bin/env python3

import cv2
import numpy
import tempfile
import time
from pathlib import Path
import logging

from multiprocessing import Process

logging.basicConfig(level=logging.INFO)
logger = logging


class ImageCompressTest(object):
    def main(self):
        image_worker = ImageWorker()
        image_worker.start()
        image_worker.join()


class ImageWorker(Process):

    ### 1k
    width  = 1920
    height = 1080

    ### 4k
    #width  = 3840
    #height = 2160

    jpg_factor_list = (100, 90, 80, 70)
    png_factor_list = (9, 8, 7, 6)


    def __init__(self):
        super(ImageWorker, self).__init__()

        self.name = 'ImageWorker000'

        logger.info('*** Generating random %d x %d image ***', self.width, self.height)
        self.random_rgb = numpy.random.randint(255, size=(self.width, self.height, 3), dtype=numpy.uint8)
        #self.random_rgb = numpy.zeros([self.width, self.height, 3], dtype=numpy.uint8)


    def run(self):
        #PNG
        logger.info('*** Running png compression tests ***')

        for png_factor in self.png_factor_list:
            logger.info('Testing png factor %d', png_factor)

            for x in range(3):
                png_tmp_file = tempfile.NamedTemporaryFile(suffix='.png', dir='/dev/shm', delete=False)
                png_tmp_file.close()

                png_tmp_file_p = Path(png_tmp_file.name)
                png_tmp_file_p.unlink()


                write_img_start = time.time()

                cv2.imwrite(str(png_tmp_file_p), self.random_rgb, [cv2.IMWRITE_JPEG_QUALITY, png_factor])

                write_img_elapsed_s = time.time() - write_img_start
                logger.info('Pass %d - compressed in %0.4f s', x, write_img_elapsed_s)

                png_tmp_file_p.unlink()


        #JPG
        logger.info('*** Running jpeg compression tests ***')

        for jpg_factor in self.jpg_factor_list:
            logger.info('Testing factor %d', jpg_factor)

            for x in range(3):
                jpg_tmp_file = tempfile.NamedTemporaryFile(suffix='.jpg', dir='/dev/shm', delete=False)
                jpg_tmp_file.close()

                jpg_tmp_file_p = Path(jpg_tmp_file.name)
                jpg_tmp_file_p.unlink()

                write_img_start = time.time()

                cv2.imwrite(str(jpg_tmp_file_p), self.random_rgb, [cv2.IMWRITE_JPEG_QUALITY, jpg_factor])

                write_img_elapsed_s = time.time() - write_img_start
                logger.info('Pass %d - compressed in %0.4f s', x, write_img_elapsed_s)

                jpg_tmp_file_p.unlink()


if __name__ == "__main__":
    ct = ImageCompressTest()
    ct.main()

