from typing import Dict
from networks.classes.centernet.datasets.PreprocessingDataset import PreprocessingDataset


class Preprocessor:

    def __init__(self, dataset_params, log):
        self.__dataset_params = dataset_params
        self.__log = log

    def preprocess_data(self, model_params: Dict) -> (PreprocessingDataset, Dict):
        """
        Creates and runs a CNN which takes an image/page of manuscript as input and predicts the
        average dimensional ratio between the characters and the image itself

        :param model_params: the parameters related to the network
        :return: a ratio predictor
        """

        # Add dataset params to model params for simplicity
        model_params.update(self.__dataset_params)

        self.__log.info('Preprocessing the data...')

        # Build dataset for the preprocessing model
        preprocessed_dataset = PreprocessingDataset(model_params)
        preprocessed_dataset.generate_dataset()

        # Dictionary that map each char category into an integer value
        dict_cat = preprocessed_dataset.get_categories_dict()

        return preprocessed_dataset, dict_cat
