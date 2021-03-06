import os

import keras.backend as kb
from tensorflow.keras.layers import *
from tensorflow.keras.losses import mean_squared_error
from tensorflow.keras.models import *
from tensorflow.keras.optimizers import RMSprop

from networks.classes.centernet.datasets.DetectionDataset import DetectionDataset
from networks.classes.centernet.models.ModelCenterNet import ModelCenterNet


class HourglassNetwork:

    def __init__(self, run_id, log, model_params, num_classes, num_stacks, num_channels, in_res, out_res):

        self.__log = log
        self.__experiment_path = os.path.join(os.getcwd(), 'network', 'experiments', run_id + '_2')
        self.__model_params = model_params

        self.__num_classes = num_classes
        self.__num_stacks = num_stacks
        self.__num_channels = num_channels
        self.__in_res = in_res
        self.__out_res = out_res

        self.__model = None

        self.__build()

    def load_model(self, model_json, model_file):
        with open(model_json) as f:
            self.__model = model_from_json(f.read())

        self.__model.load_weights(model_file)

    def train(self, dataset_params, train_list, test_list, weights_path):

        batch_size = self.__model_params['batch_size']
        epochs = self.__model_params['epochs']
        init_epoch = self.__model_params['initial_epoch']

        dataset_params['batch_size'] = self.__model_params['batch_size']
        dataset_params['batch_size_predict'] = self.__model_params['batch_size_predict']

        # Generate the dataset for detection
        dataset_detection = DetectionDataset(dataset_params)
        _, _ = dataset_detection.generate_dataset(train_list, test_list)
        training_set, detection_ts_size = dataset_detection.get_training_set()
        validation_set, detection_vs_size = dataset_detection.get_validation_set()

        # Set up the callbacks
        callbacks = ModelCenterNet.setup_callbacks(weights_log_path=weights_path,
                                                   batch_size=batch_size)

        self.__log.info('Training the model...\n')

        # Display the architecture of the model
        self.__log.info('Architecture of the model:')
        self.__model.summary()

        # Train the model
        self.__log.info('Starting the fitting procedure:')
        self.__log.info('* Total number of epochs:   ' + str(epochs))
        self.__log.info('* Initial epoch:            ' + str(init_epoch) + '\n')

        self.__model.fit(training_set,
                         epochs=epochs,
                         steps_per_epoch=int(detection_ts_size // batch_size) + 1,
                         validation_data=validation_set,
                         validation_steps=int(detection_vs_size // batch_size) + 1,
                         callbacks=callbacks,
                         initial_epoch=init_epoch)

        self.__log.info('Training procedure performed successfully!\n')

    # def resume_training(self, batch_size, model_json, model_weights, init_epoch, epochs):
    #
    #     self.load_model(model_json, model_weights)
    #     self.__model.compile(optimizer=RMSprop(lr=5e-4),
    #                          loss=mean_squared_error,
    #                          metrics=["accuracy"])
    #
    #     train_dataset = MPIIDataGen("../../data/mpii/mpii_annotations.json", "../../data/mpii/images",
    #                                 in_res=self.__in_res,
    #                                 out_res=self.__out_res,
    #                                 is_train=True)
    #
    #     train_gen = train_dataset.generator(batch_size,
    #                                         self.__num_stacks,
    #                                         sigma=1,
    #                                         is_shuffle=True,
    #                                         rot_flag=True,
    #                                         scale_flag=True,
    #                                         flip_flag=True)
    #
    #     model_dir = os.path.dirname(os.path.abspath(model_json))
    #     print(model_dir, model_json)
    #     csv_logger = CSVLogger(os.path.join(model_dir,
    #                                         "csv_train_" + str(datetime.datetime.now().strftime('%H:%M')) + ".csv"))
    #
    #     checkpoint = self.EvalCallBack(model_dir, self.__in_res, self.__out_res)
    #
    #     callbacks = [csv_logger, checkpoint]
    #
    #     self.__model.fit_generator(generator=train_gen,
    #                                steps_per_epoch=train_dataset.get_dataset_size() // batch_size,
    #                                initial_epoch=init_epoch,
    #                                epochs=epochs,
    #                                callbacks=callbacks)

    # def inference_file(self, img_file, mean=None):
    #     """
    #     Performs inference on an image file
    #
    #     :param img_file: the image file which the inference must be performed on
    #     :param mean:
    #     :return:
    #     """
    #
    #     img_data = Image.open(img_file)
    #
    #     return self.__inference_rgb(rgb_data=img_data,
    #                                 org_shape=img_data.shape,
    #                                 mean=mean)
    #
    # def __inference_rgb(self, rgb_data, org_shape, mean=None):
    #     """
    #     Performs inference on RGB data
    #
    #     :param rgb_data: the RGB data which the inference must be performed on
    #     :param org_shape: the original shape of the image
    #     :param mean:
    #     :return:
    #     """
    #
    #     scale = (org_shape[0] * 1.0 / self.__in_res[0],
    #              org_shape[1] * 1.0 / self.__in_res[1])
    #
    #     img_data = rgb_data.resize(self.__in_res)
    #
    #     if mean is None:
    #         mean = np.array([0.4404, 0.4440, 0.4327], dtype=np.float)
    #
    #     img_data = normalize(img_data, mean)
    #
    #     input_img = img_data[np.newaxis, :, :, :]
    #
    #     out = self.__model.predict(input_img)
    #
    #     return out[-1], scale

    def __build(self, mobile=False):
        """
        Builds an Hourglass network

        :param mobile: specifies if the network is mobile type
        """

        self.__log.info('Building the model...')

        if mobile:
            self.__model = self.__create_hourglass_network(self.__bottleneck_mobile)
        else:
            self.__model = self.__create_hourglass_network(self.__bottleneck_block)

    def __create_hourglass_network(self, bottleneck):
        """
        Creates the various layers of the network
        
        :param bottleneck: a function to be called in order to create the specific type of bottleneck 
        :return: 
        """

        # Create an input layer for the network
        input_layer = Input(shape=(self.__in_res[0], self.__in_res[1], 3))

        # Create the front module of the network
        head_next_stage = self.__create_front_module(input_layer, bottleneck)

        # Initialize a list of output layers
        outputs = []

        # Stack the desired number of hourglass modules
        for i in range(self.__num_stacks):
            head_next_stage, head_to_loss = self.__hourglass_module(bottom=head_next_stage,
                                                                    bottleneck=bottleneck,
                                                                    hg_id=i)
            outputs.append(head_to_loss)

        # Create the model
        model = Model(inputs=input_layer, outputs=outputs)

        # Compile the model
        model.compile(optimizer=RMSprop(lr=5e-4),
                      loss=mean_squared_error,
                      metrics=["accuracy"])

        return model

    def __hourglass_module(self, bottom, bottleneck, hg_id):
        # Create left features: f1, f2, f4, f8
        left_features = self.__create_left_half_blocks(bottom, bottleneck, hg_id)

        # Create right features and connect them with left features
        rf1 = self.__create_right_half_blocks(left_features, bottleneck, hg_id)

        # Add 1x1 conv with two heads:
        # - head_next_stage is sent to the next stage
        # - head_parts is used for intermediate supervision
        head_next_stage, head_parts = self.__create_heads(bottom, rf1, hg_id)

        return head_next_stage, head_parts

    def __create_front_module(self, input_layer, bottleneck):
        """
        Creates the front module of the network
        
        :param input_layer: the input layer of the network 
        :param bottleneck: the type of bottleneck
        :return: the front module layers of the network
        
        Note that the front module has the following structure:
         -> input to 1/4 resolution
         - 1 7x7 conv + max pooling
         - 3 residual block
        """

        x = Conv2D(filters=64,
                   kernel_size=(7, 7),
                   strides=(2, 2),
                   padding='same',
                   activation='relu',
                   name='front_conv_1x1_x1')(input_layer)

        x = BatchNormalization()(x)

        x = bottleneck(x, self.__num_channels // 2, 'front_residual_x1')
        x = MaxPool2D(pool_size=(2, 2), strides=(2, 2))(x)

        x = bottleneck(x, self.__num_channels // 2, 'front_residual_x2')
        x = bottleneck(x, self.__num_channels, 'front_residual_x3')

        return x

    def __create_left_half_blocks(self, bottom, bottleneck, hg_layer):
        """
        Creates the left half blocks for hourglass module

        :param bottom:
        :param bottleneck:
        :param hg_layer:
        :return:

        Thanks to these block, at each max pooling step the network branches off and applies
         more convolutions at the original pre-pooled resolution.

        Note the following layer-resolution correspondence:
        - f1: 1
        - f2: 1/2
        - f4: 1/4
        - f8: 1/8
        """

        hg_name = 'hg' + str(hg_layer)

        f1 = bottleneck(bottom, self.__num_channels, hg_name + '_l1')
        x = MaxPool2D(pool_size=(2, 2), strides=(2, 2))(f1)

        f2 = bottleneck(x, self.__num_channels, hg_name + '_l2')
        x = MaxPool2D(pool_size=(2, 2), strides=(2, 2))(f2)

        f4 = bottleneck(x, self.__num_channels, hg_name + '_l4')
        x = MaxPool2D(pool_size=(2, 2), strides=(2, 2))(f4)

        f8 = bottleneck(x, self.__num_channels, hg_name + '_l8')

        return f1, f2, f4, f8

    def __bottom_layer(self, lf8, bottleneck, hg_id):
        """
        Create the lowest resolution blocks (3 bottleneck blocks + Add)
        
        :param lf8: 
        :param bottleneck: a bottleneck function
        :param hg_id: the base id code of the new layers
        :return: a bottom layer for the hourglass module
        """

        lf8_connect = bottleneck(lf8, self.__num_channels, str(hg_id) + "_lf8")

        x = bottleneck(lf8, self.__num_channels, str(hg_id) + "_lf8_x1")
        x = bottleneck(x, self.__num_channels, str(hg_id) + "_lf8_x2")
        x = bottleneck(x, self.__num_channels, str(hg_id) + "_lf8_x3")

        rf8 = Add()([x, lf8_connect])

        return rf8

    def __create_right_half_blocks(self, left_features, bottleneck, hg_layer):
        """
        Creates the right half blocks of the network

        :param left_features:
        :param bottleneck:
        :param hg_layer:
        :return:

        Convolutional and max pooling layers are used to process features down to a very low resolution.
        After reaching the lowest resolution, the network begins the top-down sequence of upsampling and
         combination of features across scales.
        """

        lf1, lf2, lf4, lf8 = left_features

        rf8 = self.__bottom_layer(lf8=lf8,
                                  bottleneck=bottleneck,
                                  hg_id=hg_layer)

        rf4 = self.__connect_left_to_right(left=lf4,
                                           right=rf8,
                                           num_channels=self.__num_channels,
                                           bottleneck=bottleneck,
                                           name='hg' + str(hg_layer) + '_rf4')

        rf2 = self.__connect_left_to_right(left=lf2,
                                           right=rf4,
                                           num_channels=self.__num_channels,
                                           bottleneck=bottleneck,
                                           name='hg' + str(hg_layer) + '_rf2')

        rf1 = self.__connect_left_to_right(left=lf1,
                                           right=rf2,
                                           num_channels=self.__num_channels,
                                           bottleneck=bottleneck,
                                           name='hg' + str(hg_layer) + '_rf1')

        return rf1

    def __create_heads(self, pre_layer_features, rf1, hg_id):
        """
        Creates two networks heads, one head will go to the next stage, one to the intermediate features

        :param pre_layer_features:
        :param rf1:
        :param hg_id:
        :return:
        """

        head = Conv2D(filters=self.__num_channels,
                      kernel_size=(1, 1),
                      activation='relu',
                      padding='same',
                      name=str(hg_id) + '_conv_1x1_x1')(rf1)

        head = BatchNormalization()(head)

        # For head as intermediate supervision, use 'linear' activation
        head_parts = Conv2D(self.__num_classes,
                            kernel_size=(1, 1),
                            activation='linear',
                            padding='same',
                            name=str(hg_id) + '_conv_1x1_parts')(head)

        head = Conv2D(self.__num_channels,
                      kernel_size=(1, 1),
                      activation='linear',
                      padding='same',
                      name=str(hg_id) + '_conv_1x1_x2')(head)

        head_m = Conv2D(self.__num_channels,
                        kernel_size=(1, 1),
                        activation='linear',
                        padding='same',
                        name=str(hg_id) + '_conv_1x1_x3')(head_parts)

        head_next_stage = Add()([head,
                                 head_m,
                                 pre_layer_features])

        return head_next_stage, head_parts

    @staticmethod
    def __bottleneck_block(bottom, num_channels, block_name):

        # Skip layer
        if kb.int_shape(bottom)[-1] == num_channels:
            skip = bottom
        else:
            skip = Conv2D(num_channels,
                          kernel_size=(1, 1),
                          activation='relu',
                          padding='same',
                          name=block_name + 'skip')(bottom)

        # Residual: 3 conv blocks as [num_out_channels/2  -> num_out_channels/2 -> num_out_channels]
        x = Conv2D(num_channels // 2,
                   kernel_size=(1, 1),
                   activation='relu',
                   padding='same',
                   name=block_name + '_conv_1x1_x1')(bottom)

        x = BatchNormalization()(x)

        x = Conv2D(num_channels // 2,
                   kernel_size=(3, 3),
                   activation='relu',
                   padding='same',
                   name=block_name + '_conv_3x3_x2')(x)

        x = BatchNormalization()(x)

        x = Conv2D(num_channels,
                   kernel_size=(1, 1),
                   activation='relu',
                   padding='same',
                   name=block_name + '_conv_1x1_x3')(x)

        x = BatchNormalization()(x)

        x = Add(name=block_name + '_residual')([skip, x])

        return x

    @staticmethod
    def __bottleneck_mobile(bottom, num_channels, block_name):
        # Skip layer
        if kb.int_shape(bottom)[-1] == num_channels:
            skip = bottom
        else:
            skip = SeparableConv2D(num_channels,
                                   kernel_size=(1, 1),
                                   activation='relu',
                                   padding='same',
                                   name=block_name + 'skip')(bottom)

        # Residual: 3 conv blocks as [num_out_channels/2  -> num_out_channels/2 -> num_out_channels]
        x = SeparableConv2D(num_channels // 2,
                            kernel_size=(1, 1),
                            activation='relu',
                            padding='same',
                            name=block_name + '_conv_1x1_x1')(bottom)

        x = BatchNormalization()(x)

        x = SeparableConv2D(num_channels // 2,
                            kernel_size=(3, 3),
                            activation='relu',
                            padding='same',
                            name=block_name + '_conv_3x3_x2')(x)

        x = BatchNormalization()(x)

        x = SeparableConv2D(num_channels,
                            kernel_size=(1, 1),
                            activation='relu',
                            padding='same',
                            name=block_name + '_conv_1x1_x3')(x)

        x = BatchNormalization()(x)

        x = Add(name=block_name + '_residual')([skip, x])

        return x

    @staticmethod
    def __connect_left_to_right(left, right, num_channels, bottleneck, name):
        """
        Connect the left block to the right ones

        :param left: connect left feature to right feature
        :param name: layer name
        :return: the connection layer between a left and right block

        Note that:
        - left  -> 1 bottleneck
        - right -> upsampling
        - Add   -> left + right
        """

        x_left = bottleneck(bottom=left,
                            num_channels=num_channels,
                            block_name=name + '_connect')

        x_right = UpSampling2D()(right)

        add = Add()([x_left, x_right])

        out = bottleneck(bottom=add,
                         num_channels=num_channels,
                         block_name=name + '_connect_conv')

        return out
