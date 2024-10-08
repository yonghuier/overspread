#! /usr/bin/env python

"""
xxxxx

~M. Nicolls
last revised: xx/xx/2007

"""

import numpy as np
import pymap3d

from .constants import *


def azAverage(input):
    x = np.mean(np.sin(input))
    y = np.mean(np.cos(input))
    return np.arctan2(x,y)


def complex_median(input,axis=0):
    return np.nanmedian(input.real,axis=axis) + np.nanmedian(input.imag,axis=axis)*1.0j


def ne_prof(Power,Range,Altitude,Model,TxPower,Pulsewidth,TxFrequency,KSYS):
    Nbeams = np.size(KSYS)
    Nranges = np.size(Range)

    k = 2.0 * pi * 2.0 * TxFrequency / v_lightspeed # k vector

    Tr = Model['Te'] / Model['Ti']

    k2D2 = k * k * ((v_epsilon0 * v_Boltzmann * Model['Te']) / (Model['Ne'] * v_elemcharge * v_elemcharge))
    
    Range2 = np.repeat(np.reshape(Range,(1,Nranges)),Nbeams,axis=0)
    if Nbeams > 1:
        Ksys2 = np.repeat(np.reshape(KSYS,(Nbeams,1)),Nranges,axis=1)
    else:
        Ksys2 = KSYS

    Ne_Parm = np.real(Power * Range2 * Range2 / (Pulsewidth * TxPower * Ksys2) * (1.0 + k2D2) * (1.0 + k2D2 + Tr))
    Ne_NoTr = np.real(Power * Range2 * Range2 / (Pulsewidth * TxPower * Ksys2) * 2.0)
    
    Psc = TxPower * Pulsewidth * Ksys2 / (Range2 * Range2)
    
    return Ne_Parm, Ne_NoTr, Psc


def range2height(rng,az,el,CLAT,CLONG,CALT):
    # 
    # Converts range to geodetic altitude
    #
    # get station geocentric lat and distance 
    Nhts = len(rng)
    Nbeams = len(el)
    alt = np.zeros((Nbeams,Nhts),dtype=float)   
    for ibm in range(Nbeams):
        for iht in range(Nhts):
            sign = np.sign(rng[iht]) # range can't be negative, so we'll flip the elevation angle and mirror the az
            if sign == -1:
                azim = ((az[ibm] + 180) + 360) % 360
            else:
                azim = az[ibm]

            _, _, GDALT = pymap3d.aer2geodetic(azim,sign*el[ibm],sign*rng[iht]*1000.,CLAT,CLONG,CALT*1000,deg=True) # uses meters...
            alt[ibm,iht] = GDALT

    return alt


# deal_data
def deal_data(beamcodes,data,BMCODES):
    #
    # This function sorts the data based on beamcode
    #
    # Brute force, not pretty
    nbeams = BMCODES.size
    ndims = data.ndim
    nrecs = data.shape[0]
    output = np.zeros(data.shape, dtype=data.dtype)
    for i in range(nbeams):
        bm = BMCODES[i]
        for j in range(nrecs):
            try:
                cols = np.where(beamcodes[j,:] == bm)[0]
                if len(cols) == 1:
                    cols = int(cols)
                    if ndims == 3:
                        output[j,i,:] = data[j,cols,:]
                    elif ndims == 2:
                        output[j,i] = data[j,cols]
                    elif ndims == 4:
                        output[j,i,:,:] = data[j,cols,:,:]
            except:
                raise RuntimeError('Beamcode error in deal_data()...')

    return output