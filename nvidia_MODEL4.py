import pandas as pd
import numpy as np
import random
import matplotlib.pyplot as plt
import cv2
import matplotlib.image as mpimg
plt.switch_backend('agg')
import math
import json
import h5py
import keras
from keras.models import Sequential, Model
from keras.layers import Convolution2D, Flatten, MaxPooling2D, Lambda, ELU
from keras.layers.core import Dense, Dropout
from keras.optimizers import Adam
from keras.callbacks import Callback
from keras.layers.normalization import BatchNormalization
from keras.regularizers import l2
from keras.callbacks import ModelCheckpoint
from sklearn.model_selection import train_test_split
# loading dataset
df = pd.read_csv('interpolated.csv')
df.drop(['index','timestamp','width','height',
         'lat','long','alt'], 1, inplace = True)
data = df.values
# center, left and right cameras
left = []
left_steer = []
right = []
right_steer = []
center = []
center_steer = []
for i in range(len(df)):
    if df['frame_id'][i] == 'left_camera':
        left.append(df['filename'][i])
        left_steer.append(df['angle'][i])
    elif df['frame_id'][i] == 'right_camera':
        right.append(df['filename'][i])
        right_steer.append(df['angle'][i])
    elif df['frame_id'][i] == 'center_camera':
        center.append(df['filename'][i])
        center_steer.append(df['angle'][i])

left_steer_new = []
right_steer_new = []
for x in left_steer:
    if x <= 0.05 and x >= -0.05:
        index = left_steer.index(x)
        left_steer.remove(x)
        left.pop(index)
    
for x in center_steer:
    if x <= 0.05 and x >= -0.05:
        index = center_steer.index(x)
        center_steer.remove(x)
        center.pop(index)
for x in right_steer:
    if x <= 0.05 and x >= -0.05:
        index = right_steer.index(x)
        right_steer.remove(x)
        right.pop(index)


length = min(len(left),len(right),len(center))
center = center[:length]
center_steer = center_steer[:length]
left = left[:length]
left_steer = left_steer[:length]
right = right[:length]
right_steer = right_steer[:length]

# Data Augmentation
# Steering angle Correction
STEERING_CORRECTION = 0.2
left_steer_new = [x + STEERING_CORRECTION for x in center_steer]
right_steer_new = [x - STEERING_CORRECTION for x in center_steer]

# concatenating data
steering_data = center_steer + left_steer_new + right_steer_new
image_data = center + left + right

# Train, Validation Split
# Ratio = 80 : 20
X_train, X_validation, y_train, y_validation = train_test_split(image_data, steering_data, test_size = 0.2, random_state = 7)

# Model Hyperparameters
PROCESSED_IMG_ROWS = 66
PROCESSED_IMG_COLS = 200
PROCESSED_IMG_CHANNELS = 3
BATCH_SIZE = 64
NB_EPOCH = 10
# function to crop and resize
def im_crop_resize(image):
    image = image[-240 :,:,:]
    image = cv2.resize(image, (PROCESSED_IMG_COLS,PROCESSED_IMG_ROWS), interpolation = cv2.INTER_AREA)
    return image 

def load_and_augment_image(image_file):
    image = mpimg.imread(image_file)
    image = im_crop_resize(image)
    return image
# for accountability and debugging
random.seed(7)
generated_steering_angles = []
def generate_batch_data(image_data, steering_data, batch_size = BATCH_SIZE):
    batch_images = np.empty([batch_size, PROCESSED_IMG_ROWS, PROCESSED_IMG_COLS, PROCESSED_IMG_CHANNELS]) 
    batch_steering = np.zeros(batch_size)   
    
    while 1:
        for batch_index in range(batch_size):
            row_index = np.random.randint(len(image_data))
            image = load_and_augment_image(image_data[row_index])
            steer_angle = steering_data[row_index]
            
            batch_images[batch_index] = image
            batch_steering[batch_index] = steer_angle
            generated_steering_angles.append(steer_angle)
        yield batch_images, batch_steering

# Model

model = Sequential()
model.add(Lambda(lambda x: x/127.5 - 1., input_shape = (PROCESSED_IMG_ROWS, PROCESSED_IMG_COLS, PROCESSED_IMG_CHANNELS)))
model.add(Convolution2D(24, 5, 5, subsample = (2, 2), activation = 'elu', name = 'Conv1'))
model.add(Convolution2D(36, 5, 5, subsample = (2, 2), activation = 'elu', name = 'Conv2'))
model.add(Convolution2D(48, 5, 5, subsample = (2, 2), activation = 'elu', name = 'Conv3'))
model.add(Convolution2D(64, 3, 3, activation = 'elu', name = 'Conv4'))
model.add(Convolution2D(64, 3, 3, activation = 'elu', name = 'Conv5'))
model.add(Flatten())
model.add(Dropout(0.2))
model.add(ELU())
model.add(Dense(100, activation = 'elu', name = 'FC1'))
model.add(Dropout(0.2))
model.add(Dense(50, activation = 'elu', name = 'FC2'))
model.add(Dropout(0.2))
model.add(Dense(10, activation = 'elu', name = 'FC3'))
model.add(Dropout(0.2))
model.add(Dense(1, activation = 'elu', name = 'FC4'))
model.summary()

# checkpoints
checkpoint = ModelCheckpoint("./model_nvidia- {epoch:003d}.h5",
                             monitor = 'val_loss',
                             verbose = 1,
                             save_best_only = True,
                             mode = 'auto')

# compile
opt = Adam(lr = 0.001)
model.compile(optimizer = opt, loss = 'mse', metrics = [])

class LifecycleCallback(keras.callbacks.Callback):
    
    def on_epoch_begin(self, epoch, logs = {}):
        pass
    
    def on_epoch_end(self, epoch, logs = {}):
        global threshold
        threshold = 1 / (epoch  + 1)
        
    def on_batch_begin(self, batch, logs = {}):
        pass
    
    def on_batch_end(self, batch, logs = {}):
        self.losses.append(logs.get('loss'))
        
    def on_train_begin(self, logs = {}):
        print('BEGIN TRAINING!...')
        self.losses = []
        
    def on_train_end(self, logs = {}):
        print('END TRAINING')
        
# Calculate the correct number of samples per epoch based on batch size

def calc_samples_per_epoch(array_size, batch_size):
    num_batches = array_size / batch_size
    samples = math.ceil(num_batches)
    samples_per_epoch = int((samples * batch_size)) 
    return samples_per_epoch

# Let the training begin !

lifecycle_callback = LifecycleCallback()

train_generator = generate_batch_data(X_train, y_train, BATCH_SIZE)
validation_generator = generate_batch_data(X_validation, y_validation, BATCH_SIZE)

samples_per_epoch = calc_samples_per_epoch(len(X_train), BATCH_SIZE)
nb_val_samples = calc_samples_per_epoch(len(X_validation), BATCH_SIZE)

history = model.fit_generator(train_generator,
                              validation_data = validation_generator,
                              samples_per_epoch = len(X_train),
                              nb_val_samples = len(X_validation),
                              nb_epoch = NB_EPOCH, verbose = 1,
                              callbacks = [lifecycle_callback])

# save model
model.save("./model1_nvidia.h5")
model_json = model.to_json()
with open("./model1_nvidia.json", "w") as json_file:
    json.dump(model_json, json_file)
model.save_weights("./model1_nvidia_weights.h5")
print("saved model to disk")

binwidth = 0.025
plt.figure()
plt.hist(generated_steering_angles, bins=np.arange(min(generated_steering_angles), max(generated_steering_angles) + binwidth, binwidth))
plt.title('Number of augmented images per steering angle')
plt.xlabel('Steering Angle')
plt.ylabel('# Augmented Images')
plt.savefig("./batchaug_steering_angles.png")

plt.figure()
print(history.history.keys())

# summarize history for epoch loss
plt.plot(history.history['loss'])
plt.plot(history.history['val_loss'])
plt.title('model loss')
plt.ylabel('loss')
plt.xlabel('epoch')
plt.legend(['train', 'validation'], loc='upper right')

plt.savefig("./model1_nvidia_loss_eps.png")

# summarize history for batch loss
plt.figure()
batch_history = lifecycle_callback.losses
plt.plot(batch_history)
plt.title('model loss')
plt.ylabel('loss')
plt.xlabel('batches')

plt.savefig("./model1_nvidia_loss_batches.png")


