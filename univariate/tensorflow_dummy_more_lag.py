# -*- coding: utf-8 -*-
"""tensorflow_dummy_more_lag.ipynb

Automatically generated by Colaboratory.

#placeholder

#import dependencies
import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, f1_score
from sklearn.utils import shuffle
from math import sqrt
import seaborn as sns
from timeit import default_timer as timer

sns.set()

#make sure colab uses gpu
tf.test.gpu_device_name()

#oversampling and undersampling function
def oversample(X_train, y_train, n_oversample = 10):
  
  #concat X_train and y_train
  overs_df = pd.concat([X_train, y_train], axis = 1)
  #sort by level
  overs_df.sort_values(by=['level'],
                       inplace=True,
                       ascending=False)


  #extract top 50 rows
  top_50 = overs_df.iloc[:50]

  #concatenate
  for i in range(n_oversample):
    overs_df = pd.concat([overs_df, top_50])
  
  overs_X_train = overs_df.iloc[:,:-1]
  overs_y_train = overs_df.iloc[:,-1]
  return(overs_X_train, overs_y_train)

def undersample(X_train, y_train, n_undersample = 1000):
  #concat X_train and y_train
  unders_df = pd.concat([X_train, y_train], axis = 1)
  #sort by level
  unders_df.sort_values(by=['level'],
                       inplace=True)
  unders_df = unders_df.iloc[n_undersample:]
  print(unders_df.head())
  unders_X_train = unders_df.iloc[:,:-1]
  unders_y_train = unders_df.iloc[:,-1]
  return(unders_X_train, unders_y_train)

#read data
rain = pd.read_csv('tsvalues_long.csv',
                   sep = ';',
                   skiprows = 5)

#cut rows to match simulation
n_rain = rain.shape[0]
rain = rain[7:n_rain-1]

rain.drop(columns = ['#Timestamp'],
                     inplace = True)

swmm = pd.read_csv('pyswmm_1000mm.csv')

#lag values to create predictors
def series_to_supervised(data, n_in=1, n_out=1, dropnan=True):
	"""
	Frame a time series as a supervised learning dataset.
	Arguments:
		data: Sequence of observations as a list or NumPy array.
		n_in: Number of lag observations as input (X).
		n_out: Number of observations as output (y).
		dropnan: Boolean whether or not to drop rows with NaN values.
	Returns:
		Pandas DataFrame of series framed for supervised learning.
	"""
	n_vars = 1 if type(data) is list else data.shape[1]
	df = pd.DataFrame(data)
	cols, names = list(), list()
	# input sequence (t-n, ... t-1)
	for i in range(n_in, 0, -1):
		cols.append(df.shift(i))
		names += [('var%d(t-%d)' % (j+1, i)) for j in range(n_vars)]
	# forecast sequence (t, t+1, ... t+n)
	for i in range(0, n_out):
		cols.append(df.shift(-i))
		if i == 0:
			names += [('var%d(t)' % (j+1)) for j in range(n_vars)]
		else:
			names += [('var%d(t+%d)' % (j+1, i)) for j in range(n_vars)]
	# put it all together
	agg = pd.concat(cols, axis=1)
	agg.columns = names
	# drop rows with NaN values
	if dropnan:
		agg.dropna(inplace=True)
	return agg

n_lag = 20

rain = series_to_supervised(rain, n_lag)

swmm = swmm[n_lag:]


#get number of predictors
n_pred = rain.shape[1]

date_time = swmm['date_time']
date_time = pd.to_datetime(date_time)
swmm.drop(columns = ['date_time'],
          inplace = True)

#introduce noise to get overfitting (only for experimental reasons!)
#noise = np.random.normal(0, 0.02, swmm.shape[0])
#swmm['level'] += noise

#cbind rain and swmm
design_df = pd.concat([rain.reset_index(drop=True),
                       swmm.reset_index(drop=True)],
                       axis = 1)

#separate X and y, training and testing
n_train = round(design_df.shape[0] * 0.8)
X_train = design_df.iloc[0:n_train,:-1]
y_train = design_df.iloc[0:n_train,-1]
X_test = design_df.iloc[n_train:,:-1]
y_test = design_df.iloc[n_train:,-1]

date_time_test = date_time.iloc[n_train:]

#oversample training set (optional)
#X_train, y_train = oversample(X_train, y_train,
#                              n_oversample=20)
#undersample training set (optional)
X_train, y_train = undersample(X_train, y_train,
                               n_undersample = 200000)

#normalize dataset
train_stats = X_train.describe().transpose()

def norm(x):
  return (x - train_stats['mean']) / train_stats['std']
normed_X_train = norm(X_train)
normed_X_test = norm(X_test)

#shuffle X_train and y_train for better validation
normed_X_train, y_train = shuffle(normed_X_train, y_train)

#define model
n_nodes = 8
def build_model():
  model = keras.Sequential([
    layers.Dense(n_nodes, activation=tf.nn.relu,
                 input_shape=[len(X_train.keys())]),
    layers.Dense(n_nodes, activation=tf.nn.relu),
    layers.Dense(1)
  ])

  optimizer = tf.keras.optimizers.Adam()

  model.compile(loss='mean_squared_error',
                optimizer=optimizer,
                metrics=['mean_absolute_error', 'mean_squared_error'])
  return model

model = build_model()
model.summary()

#train the model
class PrintDot(keras.callbacks.Callback):
  def on_epoch_end(self, epoch, logs):
    if epoch % 100 == 0: print('')
    print('.', end='')
    
early_stop = keras.callbacks.EarlyStopping(monitor = 'val_loss',
                                           patience = 10)

n_epochs = 100

history = model.fit(
    normed_X_train, y_train,
    epochs = n_epochs,
    batch_size = 128,
    validation_split = 0.4,
    verbose = 1,
    callbacks = [early_stop, PrintDot()])

#plot history

def plot_history(history):
  hist = pd.DataFrame(history.history)
  hist['epoch'] = history.epoch

  plt.figure()
  plt.xlabel('Epoch')
  plt.ylabel('Mean Abs Error [m]')
  plt.plot(hist['epoch'], hist['mean_absolute_error'],
           label='Train Error')
  plt.plot(hist['epoch'], hist['val_mean_absolute_error'],
           label = 'Val Error')
  #plt.ylim((0, 0.05))
  plt.legend()
  plt.tight_layout()
  plt.savefig('mean_abs_error_ann.png',
             dpi = 300)

  plt.figure()
  plt.xlabel('Epoch')
  plt.ylabel('Mean Square Error [$m^2$]')
  plt.plot(hist['epoch'], hist['mean_squared_error'],
           label='Train Error')
  plt.plot(hist['epoch'], hist['val_mean_squared_error'],
           label = 'Val Error')
  #plt.ylim((0.000, 0.000025))
  plt.legend()
  plt.tight_layout()
  plt.savefig('mean_squared_error.png',
             dpi = 300)
  
plot_history(history)

#use model on test set


y_pred = model.predict(normed_X_test).flatten()

rmse = sqrt(mean_squared_error(y_test, y_pred))
mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)
#nse = 1 - sum((y_pred - y_test)**2) / sum((y_test - y_test.mean())**2)
print(rmse)
print(mae)
print(r2)


#plot predictions
fig_1, ax_1 = plt.subplots()
ax_1.plot(date_time_test, y_pred, label = 'Water Level ANN')
ax_1.plot(date_time_test, y_test, label = 'Water Level SWMM')
ax_1.set_ylabel('Water Level [m]')
ax_1.legend()
fig_1.autofmt_xdate()
plt.show()
fig_1.savefig('ann_vs_swmm_time.png',
              dpi = 300)

fig_2, ax_2 = plt.subplots()
ax_2.scatter(y_pred, y_test)
ax_2.set_xlabel('Water Level ANN [m]')
ax_2.set_ylabel('Water Level SWMM [m]')
plt.show()
fig_2.savefig('ann_vs_swmm_scatter.png',
              dpi = 300)

#validation: plot specific event
#low_ind = 5900
#upp_ind = 6500
low_ind = 64880
upp_ind = 65010
fig_3, ax_3 = plt.subplots()
ax_3.plot(date_time_test[low_ind:upp_ind], y_pred[low_ind:upp_ind], label = 'Water Level ANN')
ax_3.plot(date_time_test[low_ind:upp_ind],y_test[low_ind:upp_ind], label = 'Water Level SWMM')
ax_3.set_ylabel('Water Level [m]')
ax_3.legend()
fig_3.autofmt_xdate()
plt.show()
fig_3.savefig('ann_event.png',
              dpi = 300)

#validation: compare data with overflow, f1 score
over_level = 0.5
pred_over = y_pred > over_level
test_over = y_test > over_level
pred_duration = sum(pred_over)
test_duration = sum(test_over)
print(pred_duration)
print(test_duration)
f1 = f1_score(test_over, pred_over)
print(f1)

#speed evaluation, predict test set
start = timer()
dummy_pred = model.predict(normed_X_test).flatten()
end = timer()
print((end - start)/0.8) # Time in seconds