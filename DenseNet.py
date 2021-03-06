import numpy as np
import pdb
import tensorflow as tf

slim = tf.contrib.slim

class DenseNet(object):
    def __init__(self, 
                 height=28,
                 width=28,
                 depth=1,
                 nums_classes=10,
                 trainable=True,
                 lr=0.001,
                 theta=0.5,
                 prob=0.2
                ):
        self.height = height
        self.width = width
        self.depth = depth
        self.nums_classes = nums_classes
        self.is_training = trainable
        self.lr = lr
        self.theta = theta
        self.prob = prob
        self.X = tf.placeholder(tf.float32, shape=[None, self.height, self.width, self.depth], name='inputs')
        self.Y = tf.placeholder(tf.float32, shape=[None, self.nums_classes], name="labels")
        self.logits = self.build_network()
        self.loss = self.loss_fn()
        self.accuracy = self.accuracy_fn()
        self.global_step = tf.get_variable("global", initializer=tf.constant(0), trainable=False)
        self.train_op = self.build_optimizer()
        self.pred = self.pred_fn()
        

    def bn_activation_conv(self, input_tensor, depth, size, stride, padding='same', 
                           activation=tf.nn.relu, is_training=True, bn=True, bn_scale=True, prob=0.2):
        net = input_tensor
        if bn:
            net = tf.layers.batch_normalization(inputs=net,
                                                center=True,
                                                scale=bn_scale,
                                                momentum=0.99,
                                                training=is_training
                                                )
        if activation is not None:
            net = activation(net)
        net = tf.layers.conv2d(inputs=net, filters=depth, kernel_size=size, strides=stride, padding=padding)
        net = tf.layers.dropout(inputs=net, rate=prob, training=is_training)
        return net

    def conv_bn_relu(self, input_tensor, depth, size, stride, padding='same', 
                     activation=tf.nn.relu, is_training=True, bn=True, bn_scale=True, prob=0.2):
        net = input_tensor
        net = tf.layers.conv2d(inputs=net, filters=depth, kernel_size=size, strides=stride, padding=padding)
        if bn:
            net = tf.layers.batch_normalization(inputs=net,
                                                center=True,
                                                scale=bn_scale,
                                                momentum=0.99,
                                                training=is_training
                                                )
        if activation is not None:
            net = activation(net)
        net = tf.layers.dropout(inputs=net, rate=prob, training=is_training)
        return net

    def transition_layer(self, input_tensor, theta, size, stride, padding='same', 
                        is_training=True, bn=True, bn_scale=True, prob=0.2):
        input_depth = slim.utils.last_dimension(input_tensor.get_shape(), min_rank=4)
        net = self.bn_activation_conv(input_tensor, depth=int(theta*input_depth), size=size, stride=stride, padding=padding, 
                                      is_training=self.is_training, bn=bn, bn_scale=bn_scale, prob=prob)
        # net = self.conv_bn_relu(input_tensor, depth=int(theta*input_depth), size=size, stride=stride, padding=padding,
                                # is_training=is_training, bn=bn, bn_scale=True, prob=prob)
        net = tf.layers.average_pooling2d(inputs=net, pool_size=2, strides=2, padding='same')
        return net

    def dense_block(self, input_tensor, depth, activation=tf.nn.relu, is_training=True, bn=True, bn_scale=True, prob=0.2):
        net = self.bn_activation_conv(input_tensor, depth=depth*4, size=1, stride=1, padding='same',
                                      activation=activation, is_training=is_training, bn=bn, bn_scale=True, prob=prob)
        net = self.bn_activation_conv(net, depth=depth, size=3, stride=1, padding='same', 
                                      activation=activation, is_training=is_training, bn=bn, bn_scale=True, prob=prob)
        # net = self.conv_bn_relu(input_tensor, depth=depth*4, size=1, stride=1, padding='same',
                                # activation=activation, is_training=is_training, bn=bn, bn_scale=True, prob=prob)
        # net = self.conv_bn_relu(net, depth=depth, size=3, stride=1, padding='same',
                                # activation=activation, is_training=is_training, bn=bn, bn_scale=True, prob=prob)
        return net

    def build_network(self, activation=tf.nn.relu,
                      kernel_init=None,    # tf.variance_scaling_initializer()
                      bias_init=None,    # tf.constant_initializer()
                      kernel_reg=None,    # tf.contrib.layers.l2_regularizer(scale=0.001)
                      bias_reg=None
                      ):
        # Preprocess Block, input_size = 32
        net = self.X
        net = self.bn_activation_conv(net, depth=48, size=7, stride=2, padding='same',
                                      is_training=self.is_training, bn=True, bn_scale=True, prob=self.prob)
        net = tf.layers.max_pooling2d(inputs=net, pool_size=3, strides=2, padding='same')
        # Dense Block1, k = 32, l = 6, input_size = 32
        tmp = net
        for i in range(10):
            net = self.dense_block(input_tensor=tmp, depth=24, is_training=self.is_training, prob=self.prob)
            tmp = tf.concat(values=[tmp, net], axis=3)
        tmp = self.transition_layer(input_tensor=tmp, theta=self.theta, size=1, stride=1, padding='same', 
                                    is_training=self.is_training, bn=True, bn_scale=True, prob=self.prob)
        # Dense Block2, k = 32, l = 12, input_size = 16
        for i in range(10):
            net = self.dense_block(input_tensor=tmp, depth=24, is_training=self.is_training, prob=self.prob)
            tmp = tf.concat(values=[tmp, net], axis=3)
        tmp = self.transition_layer(input_tensor=tmp, theta=self.theta, size=1, stride=1, padding='same',
                                    is_training=self.is_training, bn=True, bn_scale=True, prob=self.prob)
        # Dense Block3, k = 32, l = 48, input_size = 8
        for i in range(10):
            net = self.dense_block(input_tensor=tmp, depth=24, is_training=self.is_training, prob=self.prob)
            tmp = tf.concat(values=[tmp, net], axis=3)
        tmp = tf.layers.batch_normalization(inputs=tmp, training=self.is_training)
        tmp = activation(tmp)
        # Postprocess Block, input_size = 8
        net = tf.layers.average_pooling2d(inputs=tmp, pool_size=3, strides=2, padding='same')
        net = tf.layers.flatten(net)
        net = tf.layers.dense(inputs=net, units=self.nums_classes, activation=None)
        return net

    def loss_fn(self):
        loss = tf.nn.softmax_cross_entropy_with_logits(logits=self.logits, labels=self.Y)
        return tf.reduce_mean(loss)

    def accuracy_fn(self):
        nums_correct = tf.equal(tf.argmax(self.logits, 1), tf.argmax(self.Y, 1))
        return tf.reduce_mean(tf.cast(nums_correct, "float"))
    
    def pred_fn(self):
        labels = tf.argmax(self.logits, 1)
        return tf.cast(labels, tf.int32)

    def build_optimizer(self):
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            self.optimizer = tf.train.AdamOptimizer(learning_rate=self.lr)
            # self.optimizer = tf.train.GradientDescentOptimizer(learning_rate=self.lr)
            # self.optimizer = tf.train.RMSPropOptimizer(learning_rate=self.lr)
            # self.optimizer = tf.train.MomentumOptimizer(learning_rate=self.lr, momentum=0.9, use_nesterov=True)
            gradients, variables = zip(*self.optimizer.compute_gradients(self.loss))
            gradients = [None if gradient is None else tf.clip_by_norm(gradient, 5) for gradient in gradients]
            train_op = self.optimizer.apply_gradients(zip(gradients, variables), global_step=self.global_step)
            return train_op


if __name__ == '__main__':
    main()
