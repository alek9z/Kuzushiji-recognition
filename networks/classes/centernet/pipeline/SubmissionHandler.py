import os
from typing import Generator

import numpy as np
import pandas as pd
from tqdm import tqdm
import regex as re

from networks.classes.centernet.utils.BBoxesVisualizer import BBoxesVisualizer


class SubmissionHandler:

    def __init__(self, dict_cat, log):
        self.__log = log
        self.__dict_cat = dict_cat

    def write(self, predictions_gen: Generator):
        """
        Writes a submission csv file in the format:
        - names of columns : image_id, labels
        - example of row   : image_id, {label X Y} {...}
        :param predictions_gen: a list of class predictions for the cropped characters
        """

        self.__log.info('Writing submission data...')

        # Initialize an empty dataset for submission
        submission = pd.DataFrame(columns=['image_id', 'labels'])

        # Initialize an empty dict with the data for the submission
        submission_dict = {}

        # Read the test data from csv file
        path_to_test_list = os.path.join('datasets', 'test_list.csv')
        try:
            test_list = pd.read_csv(path_to_test_list,
                                    usecols=['original_image', 'cropped_images', 'bboxes'])
        except FileNotFoundError:
            raise Exception('Cannot write submission because non test list was written at {}\n'
                            'Probably predict_on_test param was set to False, thus no prediction has been made on test'
                            .format(path_to_test_list))

        # Iterate over all the predicted original images
        for _, img_data in tqdm(test_list.iterrows(), total=len(test_list.index)):

            cropped_images = list(img_data['cropped_images'].split(' '))
            bboxes = list(img_data['bboxes'].split(' '))

            for cropped_image, bbox in zip(cropped_images, bboxes):

                # Get prediction from generator
                try:
                    prediction = next(predictions_gen)
                except StopIteration:
                    break

                # Get the unicode class from the predictions
                class_index = np.argmax(prediction)
                unicode = list(self.__dict_cat.keys())[list(self.__dict_cat.values()).index(class_index)]

                # Get the coordinates of the bbox
                ymin, xmin, ymax, xmax = bbox.split(':')

                ymin = round(float(ymin))
                xmin = round(float(xmin))
                ymax = round(float(ymax))
                xmax = round(float(xmax))

                x = str(xmin + ((xmax - xmin) // 2))
                y = str(ymin + ((ymax - ymin) // 2))

                # Append the current label to the list of the labels of the current images
                submission_dict.setdefault(img_data['original_image'], []).append(
                    ' '.join([unicode, x, y]))

        # Convert the row in format: <image_id>, <label 1> <X_1> <Y_1> <label_2> <X_2> <Y_2> ...
        for original_image, labels in submission_dict.items():
            submission_dict[original_image] = ' '.join(labels)

        # Fill the dataframe with the data from the dict
        submission['image_id'] = submission_dict.keys()
        submission['labels'] = submission_dict.values()

        # Write the submission to csv
        path_to_submission = os.path.join('datasets', 'submission.csv')
        submission.to_csv(path_to_submission)

        self.__log.info('Written submission data at {}'.format(path_to_submission))

    def test(self, max_visualizations=5):

        self.__log.info('Testing the submission...')

        # Read the submission data from csv file
        path_to_submission = os.path.join('datasets', 'submission.csv')
        try:
            submission = pd.read_csv(path_to_submission, usecols=['image_id', 'labels'])
        except FileNotFoundError:
            raise Exception(
                'Cannot fetch data for visualization because no submission was written at {}\n'
                'Probably predict_on_test param was set to False, thus no submission has been written'
                    .format(path_to_submission))

        # Initialize a bboxes visualizer object to print bboxes on images
        bbox_visualizer = BBoxesVisualizer(path_to_images=os.path.join('datasets', 'kaggle', 'testing', 'images'))

        # i counts the number of images that can be visualized
        i = 0

        # Iterate over the images
        for _, sub_data in submission.iterrows():

            if i == max_visualizations:
                break

            labels = [label.strip().split(' ') for label in re.findall(r"(?:\s?\S*\s){2}\S*", sub_data['labels'])]
            labels = [[label[0], int(label[1]), int(label[2]), 5, 5] for label in labels]

            img_id = sub_data['image_id']
            self.__log.info('Visualizing image {}'.format(img_id))
            bbox_visualizer.visualize_bboxes(image_id=img_id, labels=labels)

            i += 1