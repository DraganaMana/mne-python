"""
Example on sleep data
=====================

This tutorial explains how to perform a toy polysomnography analysis that
answers the following question:

Given two subjects from the Sleep Physionet dataset [1]_ [2]_, namely *Alice*
and *Bob*. How well can we predict the sleep stages of *Bob* from *Alice* data.

This is a supervised multiclass classification task, and this tutorial covers:

.. contents:: Contents
   :local:
   :depth: 2

"""

# Authors: Alexandre Gramfort <alexandre.gramfort@inria.fr>
#          Stanislas Chambon <stan.chambon@gmail.com>
#          Joan Massich <mailsik@gmail.com>
#
# License: BSD Style.

import numpy as np
import matplotlib.pyplot as plt

import mne
from mne.datasets.sleep_physionet import fetch_data

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

##############################################################################
# .. _plot_sleep_load_data:
#
# Load the data
# -------------
#
# Here we download the data from two subjects and the end goal is to obtain
# :term:`epochs` and its associated ground truth.
#
# To achieve this, the ``sleep_physionet`` fetcher downloads the data and
# provides us for each subject, a pair of files: ``-PSG.edf`` containing
# the :term:`raw` data from the EEG helmet, and ``-Hypnogram.edf`` containing
# the :term:`annotations` recorded by an expert. Combining this two in a 
# :class:`mne.io.Raw` object then we can extract :term:`events` based on the
# descriptions of the annotations to obtain the :term:`ephocs`
#

##############################################################################
# Read the PSG data and Hypnograms to create a :class:`mne.io.Raw` object
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ALICE, BOB = 0, 1

[alice_files, bob_files] = fetch_data(subjects=[ALICE, BOB])

mapping = {'EOG horizontal': 'eog',
           'Resp oro-nasal': 'misc',
           'EMG submental': 'misc',
           'Temp rectal': 'misc',
           'Event marker': 'misc'}

raw_train = mne.io.read_raw_edf(alice_files[0])
annot_train = mne.read_annotations(alice_files[1])

raw_train.set_annotations(annot_train)
raw_train.set_channel_types(mapping)

raw_test = mne.io.read_raw_edf(bob_files[0])
annot_test = mne.read_annotations(bob_files[1])

raw_test.set_annotations(annot_test)
raw_test.set_channel_types(mapping)

# plot some data
raw_train.plot(duration=60)

##############################################################################
# Extract 30s events from annotations
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# In this case we use the ``event_id`` parameter to select which events are we
# interested on and we associate an event identifier to each of them.


annotation_desc_2_event_id = {'Sleep stage W': 1,
                              'Sleep stage 1': 2,
                              'Sleep stage 2': 3,
                              'Sleep stage 3': 4,
                              'Sleep stage 4': 4,
                              'Sleep stage R': 5}

events_train, _ = mne.events_from_annotations(
    raw_train, event_id=annotation_desc_2_event_id, chunk_duration=30.)

events_test, _ = mne.events_from_annotations(
    raw_test, event_id=annotation_desc_2_event_id, chunk_duration=30.)

# create a new event_id that unifies stages 3 and 4
event_id = {'Sleep stage W': 1,
            'Sleep stage 1': 2,
            'Sleep stage 2': 3,
            'Sleep stage 3/4': 4,
            'Sleep stage R': 5}

# plot events
mne.viz.plot_events(events_train, event_id=event_id,
                    sfreq=raw_train.info['sfreq'])

##############################################################################
# Epoching
# ~~~~~~~~

tmax = 30. - 1. / raw_train.info['sfreq']  # tmax in included
epochs_train = mne.Epochs(raw=raw_train, events=events_train,
                          event_id=event_id, tmin=0., tmax=tmax, baseline=None)

tmax = 30. - 1. / raw_test.info['sfreq']  # tmax in included
epochs_test = mne.Epochs(raw=raw_test, events=events_test, event_id=event_id,
                         tmin=0., tmax=tmax, baseline=None)

print(epochs_train)
print(epochs_test)


##############################################################################
# .. _plot_sleep_extract_features:
#
# Extract features
# ----------------
# 
# Observing the power spectrum density (PSD) plot of the :term:`epochs` group
# by sleeping stage we can see that different sleep stages have different
# signatures. The rest of this section we will create EEG features based on
# relative power in specific frequency bands to discrete to capture difference
# between the sleep stages in our data.

_, ax = plt.subplots()

for stage in zip(epochs_train.event_id):
    epochs_train[stage].plot_psd(area_mode=None, ax=ax, fmin=0.1, fmax=20.)

prop_cycle = plt.rcParams['axes.prop_cycle']
colors = prop_cycle.by_key()['color']
[line.set_color(color) for line, color in zip(ax.get_lines(), colors)]
plt.legend(list(epochs_train.event_id.keys()))

# Extract features from EEG: relative power in specific frequency bands

eeg_channels = ["EEG Fpz-Cz", "EEG Pz-Oz"]

# specific frequency bands
freq_bands = {"delta": [0.5, 4.5],
              "theta": [4.5, 8.5],
              "alpha": [8.5, 11.5],
              "sigma": [11.5, 15.5],
              "beta": [15.5, 30]}

# extract features from training data
epochs_train.load_data().pick_channels(eeg_channels)
z_norm = np.linalg.norm(epochs_train.get_data(), axis=-1)

X_train = np.zeros(
    (epochs_train.events.shape[0], len(eeg_channels) * len(freq_bands)))
for idx_band, (band, lims) in enumerate(freq_bands.items()):
    print(idx_band, band, lims)

    z = np.linalg.norm(
        epochs_train.copy().filter(lims[0], lims[1]).get_data(),
        axis=-1) / z_norm

    X_train[
        :, len(eeg_channels) * idx_band:len(eeg_channels) * (idx_band + 1)] = z

# extract features from testing data
epochs_test.load_data().pick_channels(eeg_channels)
z_norm = np.linalg.norm(epochs_test.get_data(), axis=-1)

X_test = np.zeros(
    (epochs_test.events.shape[0], len(eeg_channels) * len(freq_bands)))
for idx_band, (band, lims) in enumerate(freq_bands.items()):
    print(idx_band, band, lims)

    z = np.linalg.norm(
        epochs_test.copy().filter(lims[0], lims[1]).get_data(),
        axis=-1) / z_norm

    X_test[
        :, len(eeg_channels) * idx_band:len(eeg_channels) * (idx_band + 1)] = z

# format annotations
y_train = events_train[:, 2]
y_test = events_test[:, 2]

##############################################################################
# Train a classifier and predict on test recording

clf = RandomForestClassifier().fit(X_train, y_train)

acc = accuracy_score(y_test, clf.predict(X_test))
print("Accuracy score: {}".format(acc))


##############################################################################
# References
# ----------------------
#
# .. [1] B Kemp, AH Zwinderman, B Tuk, HAC Kamphuisen, JJL Oberyé. Analysis of
#        a sleep-dependent neuronal feedback loop: the slow-wave
#        microcontinuity of the EEG. IEEE-BME 47(9):1185-1194 (2000).
#
# .. [2] Goldberger AL, Amaral LAN, Glass L, Hausdorff JM, Ivanov PCh,
#        Mark RG, Mietus JE, Moody GB, Peng C-K, Stanley HE. (2000)
#        PhysioBank, PhysioToolkit, and PhysioNet: Components of a New
#        Research Resource for Complex Physiologic Signals.
#        Circulation 101(23):e215-e220
