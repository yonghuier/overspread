#! /usr/bin/env python

"""
xxxxx

~M. Nicolls
last revised: xx/xx/2007

"""

import scipy.interpolate
import numpy as np

from . import io_utils
from .proc_utils import *
from .constants import *

def trim_Ibeams(inDict,Ibeams,Nbeams):

    keyz = list(inDict.keys())
    for ik in range(len(keyz)):
    
        if isinstance(inDict[keyz[ik]], dict):
            keyz2 = list(inDict[keyz[ik]].keys())
            for ik2 in range(len(keyz2)):
                nd = np.ndim(inDict[keyz[ik]][keyz2[ik2]])
                if nd > 0:
                    if inDict[keyz[ik]][keyz2[ik2]].shape[0] == Nbeams:
                        inDict[keyz[ik]][keyz2[ik2]] = inDict[keyz[ik]][keyz2[ik2]][Ibeams]

        else:
            nd = np.ndim(inDict[keyz[ik]])
            if nd > 0:
                if inDict[keyz[ik]].shape[0] == Nbeams:
                    inDict[keyz[ik]] = inDict[keyz[ik]][Ibeams]

    return inDict


# A function to compute the perturbation noise acf based on the assumption that such noise
# is white and broadband (at least compared to the width of the filter)
def compute_noise_acf(num_lags,sample_time,impulse_response):

    t_num_taps = impulse_response.size
    t_times = np.arange(t_num_taps)*1e-6
    t_acf = np.convolve(impulse_response,impulse_response)[t_num_taps-1:]
    t_acf = t_acf / t_acf[0]

    t_lag_times = np.arange(num_lags)*sample_time
    interp_func = scipy.interpolate.interp1d(t_times,t_acf,bounds_error=0, fill_value=0)
    noise_acf = interp_func(t_lag_times)

    return noise_acf


def check_noise(noise, power, noise_pulses_integrated, power_pulses_integrated):
    num_rng_data_noise = 20

    # Now check to see how "good" this noise estimate is. Compare it against
    # the power at "long ranges"
    num_noise_rng = noise.shape[2]

    # Get the average noise for each time and beam
    temp_noise = noise/(noise_pulses_integrated)
    temp_noise = np.median(temp_noise,axis=2) #(time,beams)
    output_noise_pulses_integrated = noise_pulses_integrated

    # Now get and estimate of the noise from the data power measurement
    noise_long_rng_data = power/(power_pulses_integrated)
    noise_long_rng_data = np.median(noise_long_rng_data[:,:,-num_rng_data_noise:],axis=2)
    temp_power_pulses_integrated = np.sum(power_pulses_integrated,axis=2)

    # We are going to compare the estimates up to their standard deviations
    std_temp_noise = temp_noise/np.sqrt(np.sum(noise_pulses_integrated,axis=2) + num_noise_rng)
    std_noise_long_rng_data = noise_long_rng_data/np.sqrt(np.sum(power_pulses_integrated,axis=2) + num_rng_data_noise)

    # Sometimes, pulses integrated is 0, so the power is 0. We need to make sure our long range noise estimate isn't too small
    # compare within 3 sigma (only replace if noise samples are way off)
    ind1, ind2 = np.where((np.absolute(noise_long_rng_data-temp_noise) > 3*(std_noise_long_rng_data + std_temp_noise))
                       & (temp_noise > noise_long_rng_data) & (noise_long_rng_data > 100.))

    # Replace any bad noise estimates with power based noise estimates
    output_noise = noise

    if len(ind1) > 0:
        temp_noise = noise_long_rng_data[ind1,ind2] * (temp_power_pulses_integrated[ind1,ind2] + num_rng_data_noise)
        output_noise[ind1,ind2,:] = np.repeat(temp_noise[:,np.newaxis],num_noise_rng,axis=1)
        temp_pulses_integrated = temp_power_pulses_integrated[ind1,ind2]
        output_noise_pulses_integrated[ind1,ind2,:] = np.repeat(temp_pulses_integrated[:,np.newaxis],num_noise_rng,axis=1)

    return output_noise, output_noise_pulses_integrated


def process_altcodecs(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None,h5PwrPath='/S/ZeroLags'):
    
    # function to use for data combining
    funcname='np.nanmean'
    if acfopts['procMedian']==1:
        funcname='complex_median'
                    
    # external calibration 1 means to use cal from another pulse
    if extCal==1:
        try:
            fcontsCal=fconts[1]
            fconts=fconts[0]
        except:
            print('External cal problem'        )

    # whether to use 1st lag for power estimates
    uselag1=acfopts['uselag1']
    
    try:        
        fconts[h5PwrPath]
    except:
        h5PwrPath=h5DataPath

    # initialize signal dict
    S={} 
    S['Acf']={}
    S['Power']={}

    # initialize noise 
    N={}
    N['Acf']={}
    N['Power']={}
    
    #fconts['/S/Noise']=fconts['/IncohCode/Noise'].copy()
    #fconts['/S/Noise/Power']=fconts['/IncohCode/Noise/Power'].copy()

    # initialize cal 
    C={}
    C['Power']={}
    C['Pcal']=fconts['/Rx']['Bandwidth']*fconts['/Rx']['CalTemp']*v_Boltzmann # Cal power in Watts

    # some generic stuff
    S['Acf']['Pulsewidth']=fconts[h5DataPath]['Pulsewidth']
    S['Acf']['TxBaud']=fconts[h5DataPath]['TxBaud']     
    S['Power']['Pulsewidth']=fconts[h5PwrPath]['Pulsewidth']
    S['Power']['TxBaud']=fconts[h5PwrPath]['TxBaud']
    Nbauds=np.round_(S['Acf']['Pulsewidth']/S['Acf']['TxBaud'])

    # Antenna if necessary
    if acfopts['MOTION_TYPE']==1:   
        az=fconts['/Antenna']['Azimuth'][Irecs]
        el=fconts['/Antenna']['Elevation'][Irecs]
        I=np.where(el>90.0)[0]; el[I]=180.0-el[I]; az[I]=az[I]+180.0
        I=np.where(az>360.0)[0]; az[I]=az[I]-360.0
        I=np.where(az<0.0)[0]; az[I]=az[I]+360.0
        S['AvgAzimuth']=azAverage(az*pi/180.0)*180.0/pi
        S['AvgElevation']=np.mean(el)
        S['Azimuth']=np.array([az[0,0],az[-1,-1]])
        S['Elevation']=np.array([el[0,0],el[-1,-1]])
    
    # ACF
    S['Acf']['Data']=fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,:,0].astype(complex)
    S['Acf']['Data'].imag=fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,:,1]
    (Nrecs,Nbeams,Nlags,Nranges)=S['Acf']['Data'].shape
    S['Acf']['Range']=fconts[h5DataPath+'/Acf']['Range'][[0]];
    S['Acf']['Lags']=fconts[h5DataPath+'/Acf']['Lags']
    if Nlags==Nbauds:
        S['Acf']['Kint']=1.0/np.arange(Nbauds,0.0,-1.0)
    else: # fractional lag       
        try:
            Lagind=fconts[h5DataPath+'/Acf']['Lagind']
            Lagmat=fconts[h5DataPath+'/Acf']['Lagmat']
            maxLag=Lagmat.max()+1
            if Nlags!=maxLag: # need to sum
                tdata=S['Acf']['Data']
                tlags=S['Acf']['Lags']
                S['Acf']['Data']=np.zeros((Nrecs,Nbeams,maxLag,Nranges),dtype=tdata.dtype)
                S['Acf']['Lags']=np.zeros((1,maxLag),dtype=tlags.dtype)
                for ilag in range(Nlags):
                    S['Acf']['Data'][:,:,Lagmat[ilag],:]+=tdata[:,:,ilag,:]
                    S['Acf']['Lags'][0,Lagmat[ilag]]=tlags[0,ilag]
                    #S['Acf']['Kint']=???
                Nlags=maxLag
            S['Acf']['Kint']=np.ones((maxLag))/(Nbauds)                  
        except:
            S['Acf']['Kint']=np.ones((Nlags))/(Nbauds)    #????              
    S['Acf']['Lag1Index']=np.where(np.absolute(np.squeeze(S['Acf']['Lags'])-S['Acf']['TxBaud'])==np.absolute(np.squeeze(S['Acf']['Lags'])-S['Acf']['TxBaud']).min())[0][0]

    # Now let's test if the noise estimates are "good enough" or should be replaced
    # by comparing the noise estimates against furthest ranges of data
    input_power = fconts[h5PwrPath + '/Power']['Data'][Irecs,:,:]
    input_noise = fconts['/IncohcodeCS/Noise/Power']['Data'][Irecs,:,:]

    input_power_pulses_integrated = fconts[h5PwrPath]['PulsesIntegrated'][Irecs,:]
    input_noise_pulses_integrated = fconts['/IncohcodeCS/Noise']['PulsesIntegrated'][Irecs,:]

    output_noise, output_noise_pulses_integrated = check_noise(input_noise, input_power,
                                                               input_noise_pulses_integrated,
                                                               input_power_pulses_integrated)

    # Power
    S['Power']['Data']=input_power
    N['Power']['Data']=output_noise
    S['Power']['Range']=fconts[h5PwrPath + '/Power']['Range'][[0]]; 
    S['Power']['Kint']=1.0
    if extCal==0:
        C['Power']['Data']=fconts['/IncohcodeCS/Cal/Power']['Data'][Irecs,:,:]
    elif extCal==1:
        C['Power']['Data']=fcontsCal['/IncohcodeCS/Cal/Power']['Data'][Irecs,:,:]
        C['Power']['NoiseData']=fcontsCal['/IncohcodeCS/Noise/Power']['Data'][Irecs,:,:]    
    
    # Pulses Integrated
    S['Acf']['PulsesIntegrated']=fconts[h5DataPath]['PulsesIntegrated'][Irecs,:]
    S['Power']['PulsesIntegrated']=input_power_pulses_integrated
    N['Power']['PulsesIntegrated']=output_noise_pulses_integrated
    if extCal==0:
        C['Power']['PulsesIntegrated']=fconts['/IncohcodeCS/Cal']['PulsesIntegrated'][Irecs,:]
    elif extCal==1:
        C['Power']['PulsesIntegrated']=fcontsCal['/IncohcodeCS/Cal']['PulsesIntegrated'][Irecs,:]
        C['Power']['NoisePulsesIntegrated']=fcontsCal['/IncohcodeCS/Noise']['PulsesIntegrated'][Irecs,:]
        
    # Beamcodes
    S['Acf']['Beamcodes']=fconts[h5DataPath]['Beamcodes'][Irecs,:]
    S['Power']['Beamcodes']=fconts[h5PwrPath]['Beamcodes'][Irecs,:]
    N['Power']['Beamcodes']=fconts['/IncohcodeCS/Noise']['Beamcodes'][Irecs,:]
    if extCal==0:
        C['Power']['Beamcodes']=fconts['/IncohcodeCS/Cal']['Beamcodes'][Irecs,:]
    elif extCal==1:
        C['Power']['Beamcodes']=fcontsCal['/IncohcodeCS/Cal']['Beamcodes'][Irecs,:]
        C['Power']['NoiseBeamcodes']=fcontsCal['/IncohcodeCS/Noise']['Beamcodes'][Irecs,:]
        
    # Ambiguity function path
    if doamb:
        try:
            S['Acf']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts[h5DataPath]['Ambiguity'])])
            if uselag1: # here the power is being set by the first lag of the ACF
                S['Power']['Ambiguity']=S['Acf']['Ambiguity'].copy()
                S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][1,:] 
                S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][1,:]
        except:
            print('Unable to load ambiguity function')
        try:
            S['Power']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts[h5PwrPath]['Ambiguity'])])
            # for the alternating code, set the ambiguity of the 0 lag to that of the S mode
            S['Acf']['Ambiguity']['Wlag'][0,:]=scipy.interpolate.interp1d(S['Power']['Ambiguity']['Delay'], S['Power']['Ambiguity']['Wlag'],bounds_error=0,fill_value=0.0)(S['Acf']['Ambiguity']['Delay']) # linear interpolation
            S['Acf']['Ambiguity']['Wrange'][0,:]=scipy.interpolate.interp1d(S['Power']['Ambiguity']['Range'], S['Power']['Ambiguity']['Wrange'],bounds_error=0,fill_value=0.0)(S['Acf']['Ambiguity']['Range']) # linear interpolation
            if not uselag1:
                # for the power, we are dealing only with the zero lags
                S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][0,:] 
                S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][0,:]             
        except:
            ''
        try:
            Amb=S['Acf']['Ambiguity']
        except:
            ''
            
    if acfopts['MOTION_TYPE']==0:
        # Deal the data
        beamcodes=np.sort(S['Acf']['Beamcodes'][0,:])
        # signal
        S['Power']['Data']=deal_data(S['Power']['Beamcodes'],S['Power']['Data'],beamcodes)
        S['Acf']['Data']=deal_data(S['Acf']['Beamcodes'],S['Acf']['Data'],beamcodes)
        S['Power']['PulsesIntegrated']=deal_data(S['Power']['Beamcodes'],S['Power']['PulsesIntegrated'],beamcodes)
        S['Acf']['PulsesIntegrated']=deal_data(S['Acf']['Beamcodes'],S['Acf']['PulsesIntegrated'],beamcodes)
        # noise
        N['Power']['Data']=deal_data(N['Power']['Beamcodes'],N['Power']['Data'],beamcodes)
        N['Power']['PulsesIntegrated']=deal_data(N['Power']['Beamcodes'],N['Power']['PulsesIntegrated'],beamcodes)  
        # cal
        if extCal!=2:
            C['Power']['Data']=deal_data(C['Power']['Beamcodes'],C['Power']['Data'],beamcodes)
            C['Power']['PulsesIntegrated']=deal_data(C['Power']['Beamcodes'],C['Power']['PulsesIntegrated'],beamcodes)  
        if extCal==1:
            C['Power']['NoiseData']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoiseData'],beamcodes)
            C['Power']['NoisePulsesIntegrated']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoisePulsesIntegrated'],beamcodes)  

        # get the beamcodes
        if BeamCodes is None:
            if np.sum(fconts['/Setup']['BeamcodeMap'][:,3])==0.0:
                try:
                    f=open(acfopts['DEFOPTS']['BMCODEMAP_DEF'])
                    fconts['/Setup']['BeamcodeMap']=np.loadtxt(f)
                    f.close()
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['DEFOPTS']['BMCODEMAP_DEF'])
            S['BMCODES']=np.zeros((Nbeams,4),dtype=float)-1 # beamcode table (beamcode,az,el,ksys)
            for i in range(Nbeams):
                I=np.where(fconts['/Setup']['BeamcodeMap'][:,0]==beamcodes[i])[0]
                S['BMCODES'][i,:]=fconts['/Setup']['BeamcodeMap'][I,:]
                if S['BMCODES'][i,3]==0.0:
                    print('Using default system constant, %4.4e' % (acfopts['DEFOPTS']['KSYS_DEF']))
                    S['BMCODES'][i,3]=acfopts['DEFOPTS']['KSYS_DEF']
            if acfopts['beamMapScale']:
                try:
                    f=open(acfopts['beamMapScaleFile'])
                    BmScaler=np.loadtxt(f)
                    f.close()
                    print('Using Beam Code scaler from %s' % acfopts['beamMapScaleFile'] )
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['beamMapScaleFile'])
                for i in range(Nbeams):
                    I=np.where(BmScaler[:,0]==beamcodes[i])[0]
                    if len(I)>0:
                        # replace
                        S['BMCODES'][i,3]=BmScaler[I,3]
                    else:
                        raise IOError('No Beam %d in %s!' % (beamcodes[i], acfopts['beamMapScaleFile']))
        else:
            S['BMCODES']=BeamCodes
                
        Ksys=np.repeat(np.repeat(S['BMCODES'][:,3][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)

    elif acfopts['MOTION_TYPE']==1:
        try:
            S['Ksys']=fconts['/Rx']['SysConst']
        except KeyError:
            print("/Rx/SysConst not found, using hardcoded default: %s" % str(S['Ksys']))
            S['Ksys']=acfopts['DEFOPTS']['KSYS_DEF']
        Ksys=S['Ksys']
        S['BMCODES']=np.array([[-1,S['AvgAzimuth'],S['AvgElevation'],Ksys]])                

    # Average the noise and cal power samples
    N['Power']['Data']=np.nanmean(complex_median(N['Power']['Data'],axis=2)/N['Power']['PulsesIntegrated'],axis=0)
    if extCal!=2:
        C['Power']['Data']=np.mean(complex_median(C['Power']['Data'],axis=2)/C['Power']['PulsesIntegrated'],axis=0)
    if extCal==0:
        C['Power']['Data']=C['Power']['Data']-N['Power']['Data']
    elif extCal==1:
        C['Power']['NoiseData']=np.nanmean(complex_median(C['Power']['NoiseData'],axis=2)/C['Power']['NoisePulsesIntegrated'],axis=0)
        C['Power']['Data']=C['Power']['Data']-C['Power']['NoiseData']
        C['Power']['Data']=(C['Power']['Data']/C['Power']['NoiseData'])*N['Power']['Data'] # (C/Ncal)*N
    elif extCal==2:
        C['Power']['Data']=N['Power']['Data']*acfopts['CalToNoiseRatio']

    # Noise subtract and calibrate the ACF
    S['Acf']['Data']=S['Acf']['Data']/np.repeat(np.repeat(S['Acf']['PulsesIntegrated'][:,:,np.newaxis,np.newaxis],Nlags,axis=2),Nranges,axis=3) 
    S['Acf']['PulsesIntegrated']=np.sum(S['Acf']['PulsesIntegrated'],axis=0)
    S['Acf']['StDev']=np.std(np.absolute(S['Acf']['Data'][:,:,1,:]),axis=0)/np.sqrt(Nrecs)
    S['Acf']['Data']=eval(funcname+"(S['Acf']['Data'],axis=0)")
    S['Acf']['StDev']=S['Acf']['StDev']/np.absolute(S['Acf']['Data'][:,1,:])
    S['Acf']['Data']=C['Pcal']*(S['Acf']['Data'])/np.repeat(np.repeat(C['Power']['Data'][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)

    # Noise subtract and calibrate power profle
    S['Power']['Data']=S['Power']['Data']/np.repeat(S['Power']['PulsesIntegrated'][:,:,np.newaxis],Nranges,axis=2)
    S['Power']['PulsesIntegrated']=np.sum(S['Power']['PulsesIntegrated'],axis=0)
    S['Power']['StDev']=np.std(S['Power']['Data'],axis=0)/np.sqrt(Nrecs)
    S['Power']['Data']=eval(funcname+"(S['Power']['Data'],axis=0)")
    S['Power']['StDev']=S['Power']['StDev']/S['Power']['Data']
    S['Power']['Data']=C['Pcal']*(S['Power']['Data']-np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/np.repeat(C['Power']['Data'][:,np.newaxis],Nranges,axis=1)

    # convert noise to Watts
    N['Power']['Data']=C['Pcal']*(N['Power']['Data']/C['Power']['Data']) # Noise Power in Watts
    
    # scaling constant
    Ksys=np.repeat(np.repeat(S['BMCODES'][:,3][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)
    Range=np.repeat(np.repeat(np.squeeze(S['Acf']['Range'])[np.newaxis,np.newaxis,:],Nbeams,axis=0),Nlags,axis=1)
    S['Acf']['Psc']=S['Acf']['Pulsewidth']*Ksys/(Range*Range)

    # Signal to Noise ratio
    S['Power']['SNR']=np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))
    
    # Clutter to Noise ratio
    S['Acf']['iSCR']=(Nbauds-1.0)*np.ones(Nlags)
    S['Power']['iSCR']=0.0

    # set the 0 lag of the ACF to the short pulse zerolag measurement
    S['Acf']['Data'][:,0,:]=S['Power']['Data']
    S['Acf']['Psc'][:,0,:]=S['Acf']['Psc'][:,0,:]*S['Power']['Pulsewidth']/S['Acf']['Pulsewidth']
    S['Acf']['Kint'][0]=1.0
    S['Acf']['iSCR'][0]=0.0
    
    # if uselag1=1, use the 1st lag to compute the apriori density
    if uselag1:
        S['Power']['Data']=np.absolute(S['Acf']['Data'][:,S['Acf']['Lag1Index'],:])
        S['Power']['StDev']=S['Acf']['StDev']
        S['Power']['PulsesIntegrated']=S['Acf']['PulsesIntegrated']
        S['Power']['Pulsewidth']=S['Acf']['Pulsewidth']
        S['Power']['TxBaud']=S['Acf']['TxBaud']
        S['Power']['Range']=S['Acf']['Range']
        S['Acf']['Kint'][1:]=S['Acf']['Kint'][1:]*(Nbauds-1.0)**2.0
        S['Acf']['Kint'][0]=S['Acf']['Kint'][0]*(Nbauds*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))**2.0
        S['Power']['SNR']=np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/1.0 #((Nbauds-1.0)*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))
        S['Power']['iSCR']=Nbauds-1.0
        S['Power']['Kint']=Nbauds-1.0
    else:
        S['Acf']['Kint'][1:]=S['Acf']['Kint'][1:]/np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:]))**2.0
    
    return S,N,C
    
def process_altcode(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None,h5PwrPath='/S/ZeroLags'):

    # function to use for data combining
    funcname='np.nanmean'
    if acfopts['procMedian']==1:
        funcname='complex_median'
                    
    # external calibration 1 means to use cal from another pulse
    if extCal==1:
        try:
            fcontsCal=fconts[1]
            fconts=fconts[0]
        except:
            print('External cal problem'        )

    # whether to use 1st lag for power estimates
    uselag1=acfopts['uselag1']


    try:
        fconts[h5DataPath]
    except:
        h5DataPath = '/IncohCodeFl1/Data'
        
    try:        
        fconts[h5PwrPath]
    except:
        h5PwrPath=h5DataPath

        
    # initialize signal dict
    S={} 
    S['Acf']={}
    S['Power']={}

    # initialize noise 
    N={}
    N['Acf']={}
    N['Power']={}
    
    #fconts['/S/Noise']=fconts['/IncohCode/Noise'].copy()
    #fconts['/S/Noise/Power']=fconts['/IncohCode/Noise/Power'].copy()

    # initialize cal 
    C={}
    C['Power']={}
    C['Pcal']=fconts['/Rx']['Bandwidth']*fconts['/Rx']['CalTemp']*v_Boltzmann # Cal power in Watts

    # some generic stuff
    S['Acf']['Pulsewidth']=fconts[h5DataPath]['Pulsewidth']
    S['Acf']['TxBaud']=fconts[h5DataPath]['TxBaud']     
    S['Power']['Pulsewidth']=fconts[h5PwrPath]['Pulsewidth']
    S['Power']['TxBaud']=fconts[h5PwrPath]['TxBaud']
    Nbauds=np.round_(S['Acf']['Pulsewidth']/S['Acf']['TxBaud'])

    # Antenna if necessary
    if acfopts['MOTION_TYPE']==1:   
        az=fconts['/Antenna']['Azimuth'][Irecs]
        el=fconts['/Antenna']['Elevation'][Irecs]
        I=np.where(el>90.0)[0]; el[I]=180.0-el[I]; az[I]=az[I]+180.0
        I=np.where(az>360.0)[0]; az[I]=az[I]-360.0
        I=np.where(az<0.0)[0]; az[I]=az[I]+360.0
        S['AvgAzimuth']=azAverage(az*pi/180.0)*180.0/pi
        S['AvgElevation']=np.mean(el)
        S['Azimuth']=np.array([az[0,0],az[-1,-1]])
        S['Elevation']=np.array([el[0,0],el[-1,-1]])

    # Now check to see if the lag0 power array and the ACF array have the 
    # same number of range gates or not. If not, trim to the smallest.
    # Added by ASR 07/02/2017
    acf_nrange = fconts[h5DataPath+'/Acf']['Data'].shape[3]
    power_nrange = fconts[h5PwrPath + '/Power']['Data'].shape[2]

    if acf_nrange == power_nrange:
        Nranges = acf_nrange
    elif acf_nrange > power_nrange:
        Nranges = power_nrange
    else:
        Nranges = acf_nrange
    
    # ACF
    S['Acf']['Data'] = fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,0:Nranges,0].astype(complex)
    S['Acf']['Data'].imag = fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,0:Nranges,1]
    (Nrecs,Nbeams,Nlags,_) = S['Acf']['Data'].shape
    S['Acf']['Range'] = fconts[h5DataPath+'/Acf']['Range'][0,0:Nranges] # range assumed same for all beams
    S['Acf']['Range'] = S['Acf']['Range'].reshape((1,Nranges))
    S['Acf']['Lags'] = fconts[h5DataPath+'/Acf']['Lags']
    if Nlags == Nbauds:
        # S['Acf']['Kint'] = 1 / np.arange(Nbauds,0.0,-1.0)
        S['Acf']['Kint'] = np.arange(Nbauds,0.0,-1.0)
    else: # fractional lag  
        # try:
        if 1==1:
            Lagind = fconts[h5DataPath+'/Acf']['Lagind']
            Lagmat = fconts[h5DataPath+'/Acf']['Lagmat']
            maxLag = Lagmat.max()+1
            factor = np.zeros((maxLag))
            S['Acf']['Kint'] = np.zeros((maxLag))
            if Nlags != maxLag: # need to sum
                tdata = S['Acf']['Data']
                tlags = S['Acf']['Lags']
                S['Acf']['Data'] = np.zeros((Nrecs,Nbeams,maxLag,Nranges),dtype=tdata.dtype)
                S['Acf']['Lags'] = np.zeros((1,maxLag),dtype=tlags.dtype)
                for ilag in range(Nlags):
                    S['Acf']['Data'][:,:,Lagmat[ilag],:] += tdata[:,:,ilag,:]
                    S['Acf']['Lags'][0,Lagmat[ilag]] = tlags[0,ilag]
                    whole_lag_num = np.floor(S['Acf']['Lags'][0,Lagmat[ilag]] / S['Acf']['TxBaud'])
                    factor[Lagmat[ilag]] += 1
                    S['Acf']['Kint'][Lagmat[ilag]] = Nbauds - whole_lag_num
                Nlags = maxLag
            S['Acf']['Kint'] *= factor
        # except Exception as e:
        #     print('Exception: %s' % str(e))
        #     S['Acf']['Kint'] = np.ones((Nlags))/(Nbauds)

    S['Acf']['Lag1Index'] = np.where(np.absolute(np.squeeze(S['Acf']['Lags'])-S['Acf']['TxBaud']) == np.absolute(np.squeeze(S['Acf']['Lags'])-S['Acf']['TxBaud']).min())[0][0]



    input_power = fconts[h5PwrPath + '/Power']['Data'][Irecs,:,:Nranges]
    input_noise = fconts['/S/Noise/Power']['Data'][Irecs,:,:]
    noise_Nranges = input_noise.shape[2]


    # Determine the existence and dimensionality of the pulses integrated arrays
    # (implemented by ASR to handle resampled data 15/03/2017)

    # ACF pulses integrated
    try:
        acf_pulses_integrated = fconts[h5DataPath + '/Acf']['PulsesIntegrated']
    except KeyError:
        acf_pulses_integrated = fconts[h5DataPath]['PulsesIntegrated']
    if np.ndim(acf_pulses_integrated) == 2:
        acf_pulses_integrated = np.repeat(acf_pulses_integrated[:,:,np.newaxis],Nlags,axis=2)
    if np.ndim(acf_pulses_integrated) == 3:
        acf_pulses_integrated = np.repeat(acf_pulses_integrated[:,:,:,np.newaxis],Nranges,axis=3)
    acf_pulses_integrated = acf_pulses_integrated[Irecs,:,:,:]


    # Noise ACF pulses integrated
    try:
        noise_noise_acf_pulses_integrated = fconts['/S/Noise/Acf']['PulsesIntegrated']
    except KeyError:
        noise_acf_pulses_integrated = fconts['/S/Noise']['PulsesIntegrated']
    if np.ndim(noise_acf_pulses_integrated) == 2:
        noise_acf_pulses_integrated = np.repeat(noise_acf_pulses_integrated[:,:,np.newaxis],Nlags,axis=2)
    if np.ndim(noise_acf_pulses_integrated) == 3:
        noise_acf_pulses_integrated = np.repeat(noise_acf_pulses_integrated[:,:,:,np.newaxis],noise_Nranges,axis=3)
    noise_acf_pulses_integrated = noise_acf_pulses_integrated[Irecs,:,:,:]


    # Power pulses integrated
    try:
        power_pulses_integrated = fconts[h5PwrPath + '/Power']['PulsesIntegrated']
    except KeyError:
        power_pulses_integrated = fconts[h5PwrPath]['PulsesIntegrated']
    if np.ndim(power_pulses_integrated) == 2:
        power_pulses_integrated = np.repeat(power_pulses_integrated[:,:,np.newaxis],Nranges,axis=2)
    power_pulses_integrated = power_pulses_integrated[Irecs,:,:]

    # Noise pulses integrated
    try:
        noise_power_pulses_integrated = fconts['/S/Noise/Power']['PulsesIntegrated']
    except KeyError:
        noise_power_pulses_integrated = fconts['/S/Noise']['PulsesIntegrated']
    if np.ndim(noise_power_pulses_integrated) == 2:
        noise_power_pulses_integrated = np.repeat(noise_power_pulses_integrated[:,:,np.newaxis],noise_Nranges,axis=2)
    noise_power_pulses_integrated = noise_power_pulses_integrated[Irecs,:,:]


    # Anywhere that our ACFs or Powers pulses integrated is 0, we must make sure the data is zeroed out too
    S['Acf']['Data'][np.where(acf_pulses_integrated == 0)] = 0.0+0.0j
    #N['Acf']['Data'][np.where(noise_acf_pulses_integrated == 0)] = 0.0+0.0j
    input_power[np.where(power_pulses_integrated == 0)] = 0
    input_noise[np.where(noise_power_pulses_integrated == 0)] = 0


    # Now let's test if the noise estimates are "good enough" or should be replaced
    # by comparing the noise estimates against furthest ranges of data

    input_power_pulses_integrated = power_pulses_integrated
    input_noise_pulses_integrated = noise_power_pulses_integrated

    # Noise
    if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(input_noise)[-1]:
        beamloc = []
        for beam in fconts[h5DataPath]['Beamcodes'][0,:]:
            condition = (fconts['/S/Noise']['Beamcodes'][0,:] == beam)
            beamloc.append(np.where(condition)[0][0])
        beamloc = np.array(beamloc)
        input_noise=input_noise[:,beamloc,:]
        input_noise_pulses_integrated = input_noise_pulses_integrated[:,beamloc,:]

    output_noise, output_noise_pulses_integrated = check_noise(input_noise, input_power,
                                                               input_noise_pulses_integrated,
                                                               input_power_pulses_integrated)


    # Power
    S['Power']['Data']  = input_power[:,:,0:Nranges]
    N['Power']['Data']  = output_noise

    S['Power']['Range']=fconts[h5PwrPath + '/Power']['Range'][[0]]; 
    S['Power']['Kint']=1.0
    C['Power']['Data']=fconts['/S/Cal/Power']['Data'][Irecs,:,:]
    if extCal==0:
        if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Cal']['Beamcodes'])[-1]:  
            C['Power']['Data']=C['Power']['Data'][:,beamloc,:]
    elif extCal==1:
        C['Power']['Data']=fcontsCal['/S/Cal/Power']['Data'][Irecs,:,:]
        C['Power']['NoiseData']=fcontsCal['/S/Noise/Power']['Data'][Irecs,:,:]
    
    # Pulses Integrated
    S['Acf']['PulsesIntegrated']    = acf_pulses_integrated
    S['Power']['PulsesIntegrated']  = input_power_pulses_integrated[:,:,0:Nranges]
    N['Power']['PulsesIntegrated']  = output_noise_pulses_integrated

    if extCal==0:
        if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Noise']['Beamcodes'])[-1]:
            C['Power']['PulsesIntegrated']=fconts['/S/Cal']['PulsesIntegrated'][Irecs,:]
            C['Power']['PulsesIntegrated']=C['Power']['PulsesIntegrated'][:,beamloc]
        else:
            C['Power']['PulsesIntegrated']=fconts['/S/Cal']['PulsesIntegrated'][Irecs,:]
    elif extCal==1:
        if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Noise']['Beamcodes'])[-1]:
            C['Power']['PulsesIntegrated']=fcontsCal['/S/Cal']['PulsesIntegrated'][Irecs,:]
            C['Power']['NoisePulsesIntegrated']=fcontsCal['/S/Noise']['PulsesIntegrated'][Irecs,:]
            C['Power']['PulsesIntegrated']=C['Power']['PulsesIntegrated'][:,beamloc]
            C['Power']['NoisePulsesIntegrated']=C['Power']['NoisePulsesIntegrated'][:,beamloc]
        else:
            C['Power']['PulsesIntegrated']=fcontsCal['/S/Cal']['PulsesIntegrated'][Irecs,:]
            C['Power']['NoisePulsesIntegrated']=fcontsCal['/S/Noise']['PulsesIntegrated'][Irecs,:]
        
    # Beamcodes
    S['Acf']['Beamcodes']=fconts[h5DataPath]['Beamcodes'][Irecs,:]
    S['Power']['Beamcodes']=fconts[h5PwrPath]['Beamcodes'][Irecs,:]
    N['Power']['Beamcodes']=fconts['/S/Noise']['Beamcodes'][Irecs,:]
    if extCal==0:
        C['Power']['Beamcodes']=fconts['/S/Cal']['Beamcodes'][Irecs,:]
    elif extCal==1:
        C['Power']['Beamcodes']=fcontsCal['/S/Cal']['Beamcodes'][Irecs,:]
        C['Power']['NoiseBeamcodes']=fcontsCal['/S/Noise']['Beamcodes'][Irecs,:]
        
    # Ambiguity function path
    if doamb:
        try:
            S['Acf']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts[h5DataPath]['Ambiguity'])])
            if uselag1: # here the power is being set by the first lag of the ACF
                S['Power']['Ambiguity']=S['Acf']['Ambiguity'].copy()
                S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][1,:] 
                S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][1,:]
        except:
            print('Unable to load ambiguity function')
        try:
            S['Power']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts[h5PwrPath]['Ambiguity'])])
            # for the alternating code, set the ambiguity of the 0 lag to that of the S mode
            S['Acf']['Ambiguity']['Wlag'][0,:]=scipy.interpolate.interp1d(S['Power']['Ambiguity']['Delay'], S['Power']['Ambiguity']['Wlag'],bounds_error=0,fill_value=0.0)(S['Acf']['Ambiguity']['Delay']) # linear interpolation
            S['Acf']['Ambiguity']['Wrange'][0,:]=scipy.interpolate.interp1d(S['Power']['Ambiguity']['Range'], S['Power']['Ambiguity']['Wrange'],bounds_error=0,fill_value=0.0)(S['Acf']['Ambiguity']['Range']) # linear interpolation
            if not uselag1:
                # for the power, we are dealing only with the zero lags
                S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][0,:] 
                S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][0,:]             
        except:
            ''
        try:
            Amb=S['Acf']['Ambiguity']
        except:
            ''
            
    if acfopts['MOTION_TYPE']==0:
        # Deal the data
        
        beamcodes=np.sort(S['Acf']['Beamcodes'][0,:])
        # signal
        S['Power']['Data']=deal_data(S['Power']['Beamcodes'],S['Power']['Data'],beamcodes)
        S['Acf']['Data']=deal_data(S['Acf']['Beamcodes'],S['Acf']['Data'],beamcodes)
        S['Power']['PulsesIntegrated']=deal_data(S['Power']['Beamcodes'],S['Power']['PulsesIntegrated'],beamcodes)
        S['Acf']['PulsesIntegrated']=deal_data(S['Acf']['Beamcodes'],S['Acf']['PulsesIntegrated'],beamcodes)
        # noise
        if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Cal']['Beamcodes'])[-1]:
            N['Power']['Data']=deal_data(N['Power']['Beamcodes'][:,beamloc],N['Power']['Data'],beamcodes)
            N['Power']['PulsesIntegrated']=deal_data(N['Power']['Beamcodes'][:,beamloc],N['Power']['PulsesIntegrated'],beamcodes)
        else:
            N['Power']['Data']=deal_data(N['Power']['Beamcodes'],N['Power']['Data'],beamcodes)
            N['Power']['PulsesIntegrated']=deal_data(N['Power']['Beamcodes'],N['Power']['PulsesIntegrated'],beamcodes)
        # cal
        if extCal!=2:
            if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Cal']['Beamcodes'])[-1]:
                C['Power']['Data']=deal_data(C['Power']['Beamcodes'][:,beamloc],C['Power']['Data'],beamcodes)
                C['Power']['PulsesIntegrated']=deal_data(C['Power']['Beamcodes'][:,beamloc],C['Power']['PulsesIntegrated'],beamcodes)
            else:
                C['Power']['Data']=deal_data(C['Power']['Beamcodes'],C['Power']['Data'],beamcodes)
                C['Power']['PulsesIntegrated']=deal_data(C['Power']['Beamcodes'],C['Power']['PulsesIntegrated'],beamcodes)  
        if extCal==1:
            if np.shape(fconts[h5DataPath]['Beamcodes'])[-1] != np.shape(fconts['/S/Cal']['Beamcodes'])[-1]:
                C['Power']['NoiseData']=deal_data(C['Power']['NoiseBeamcodes'][:,beamloc],C['Power']['NoiseData'],beamcodes)
                C['Power']['NoisePulsesIntegrated']=deal_data(C['Power']['NoiseBeamcodes'][:,beamloc],C['Power']['NoisePulsesIntegrated'],beamcodes)  
            else:
                C['Power']['NoiseData']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoiseData'],beamcodes)
                C['Power']['NoisePulsesIntegrated']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoisePulsesIntegrated'],beamcodes)  

        # get the beamcodes
        if BeamCodes is None:
            if np.sum(fconts['/Setup']['BeamcodeMap'][:,3])==0.0:
                try:
                    f=open(acfopts['DEFOPTS']['BMCODEMAP_DEF'])
                    fconts['/Setup']['BeamcodeMap']=np.loadtxt(f)
                    f.close()
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['DEFOPTS']['BMCODEMAP_DEF'])
            S['BMCODES']=np.zeros((Nbeams,4),dtype=float)-1 # beamcode table (beamcode,az,el,ksys)
            for i in range(Nbeams):
                I=np.where(fconts['/Setup']['BeamcodeMap'][:,0]==beamcodes[i])[0]
                S['BMCODES'][i,:]=fconts['/Setup']['BeamcodeMap'][I,:]
                if S['BMCODES'][i,3]==0.0:
                    print('Using default system constant, %4.4e' % (acfopts['DEFOPTS']['KSYS_DEF']))
                    S['BMCODES'][i,3]=acfopts['DEFOPTS']['KSYS_DEF']
            if acfopts['beamMapScale']:
                try:
                    f=open(acfopts['beamMapScaleFile'])
                    BmScaler=np.loadtxt(f)
                    f.close()
                    print('Using Beam Code scaler from %s' % acfopts['beamMapScaleFile'] )
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['beamMapScaleFile'])
                for i in range(Nbeams):
                    I=np.where(BmScaler[:,0]==beamcodes[i])[0]
                    if len(I)>0:
                        # replace
                        S['BMCODES'][i,3]=BmScaler[I,3]
                    else:
                        raise IOError('No Beam %d in %s!' % (beamcodes[i], acfopts['beamMapScaleFile']))
        else:
            S['BMCODES']=BeamCodes
                
        Ksys=np.repeat(np.repeat(S['BMCODES'][:,3][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)

    elif acfopts['MOTION_TYPE']==1:
        try:
            S['Ksys']=fconts['/Rx']['SysConst']
        except KeyError:
            print("/Rx/SysConst not found, using hardcoded default: %s" % str(S['Ksys']))
            S['Ksys']=acfopts['DEFOPTS']['KSYS_DEF']
        Ksys=S['Ksys']
        S['BMCODES']=np.array([[-1,S['AvgAzimuth'],S['AvgElevation'],Ksys]])                

    # Average the noise and cal power samples
    N['Power']['Data']=np.nanmean(complex_median(N['Power']['Data']/N['Power']['PulsesIntegrated'],axis=2),axis=0)
    if extCal!=2:
        C['Power']['Data']=np.mean(complex_median(C['Power']['Data'],axis=2)/C['Power']['PulsesIntegrated'],axis=0)
    if extCal==0:
        C['Power']['Data']=C['Power']['Data']-N['Power']['Data']
    elif extCal==1:
        C['Power']['NoiseData']=np.nanmean(complex_median(C['Power']['NoiseData'],axis=2)/C['Power']['NoisePulsesIntegrated'],axis=0)
        C['Power']['Data']=C['Power']['Data']-C['Power']['NoiseData']
        C['Power']['Data']=(C['Power']['Data']/C['Power']['NoiseData'])*N['Power']['Data'] # (C/Ncal)*N
    elif extCal==2:
        C['Power']['Data']=N['Power']['Data']*acfopts['CalToNoiseRatio']

    # convert noise to Watts
    N['Power']['Data'] = C['Pcal']*(N['Power']['Data']/C['Power']['Data']) # Noise Power in Watts
    N['Power']['PulsesIntegrated']=np.sum(np.sum(N['Power']['PulsesIntegrated'],axis=2),axis=0) # total number of pulses used for the estimate

    # Noise subtract and calibrate power profle
    S['Power']['Data']=S['Power']['Data']/S['Power']['PulsesIntegrated']
    S['Power']['PulsesIntegrated']=np.sum(S['Power']['PulsesIntegrated'],axis=0)
    S['Power']['StDev']=np.std(S['Power']['Data'],axis=0)/np.sqrt(Nrecs)
    S['Power']['Data']=eval(funcname+"(S['Power']['Data'],axis=0)")
    S['Power']['StDev']=S['Power']['StDev']/S['Power']['Data']

    # SNR = S/N, we subtract off the average noise, then fit the data with a data model + perturbation noise model
    S['Power']['Data']  = C['Pcal']*S['Power']['Data']/np.repeat(C['Power']['Data'][:,np.newaxis],Nranges,axis=1)
    S['Power']['Data']  = S['Power']['Data'] - np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1)
    S['Power']['SNR']   = S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1)

    # Noise subtract and calibrate the ACF
    S['Acf']['Data'] = S['Acf']['Data']/S['Acf']['PulsesIntegrated']
    S['Acf']['PulsesIntegrated'] = np.sum(S['Acf']['PulsesIntegrated'],axis=0)
    S['Acf']['StDev'] = np.std(np.absolute(S['Acf']['Data'][:,:,1,:]),axis=0)/np.sqrt(Nrecs)
    S['Acf']['Data'] = eval(funcname+"(S['Acf']['Data'],axis=0)")
    S['Acf']['StDev'] = S['Acf']['StDev'] / np.absolute(S['Acf']['Data'][:,1,:])
    S['Acf']['Data'] = C['Pcal']*(S['Acf']['Data']) / np.repeat(np.repeat(C['Power']['Data'][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)

    # Subtract the modeled noise ACF scaled by the estimated lag0 noise power from the data ACF
    # Parameters needed for calculating the perturbation noise_acf
    
    sample_time = fconts['/Rx'].get('SampleTime',fconts['/Rx'].get('Sampletime',None))
    temp = fconts['/Setup']['RxFilterfile']
    # old files, from 2007 require this check
    if isinstance(temp,np.ndarray):
        if len(temp.shape) > 0:
            temp = temp[0]
    temp = str(temp)
    temp = temp.replace('\r','')
    filter_coefficients = np.array([float(x) for x in temp.split('\n')[:-1]])
    noise_acf = compute_noise_acf(Nlags,sample_time,filter_coefficients)
    noise_acfs = np.repeat(noise_acf[np.newaxis,:],Nbeams,axis=0)
    scaled_noise_acfs = np.repeat(N['Power']['Data'][:,np.newaxis],Nlags,axis=1)*noise_acfs
    scaled_noise_acfs = np.repeat(scaled_noise_acfs[:,:,np.newaxis],Nranges,axis=2)


    S['Acf']['Data'].real=S['Acf']['Data'].real-scaled_noise_acfs


    # scaling constant
    Ksys=np.repeat(np.repeat(S['BMCODES'][:,3][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)
    Range=np.repeat(np.repeat(np.squeeze(S['Acf']['Range'][0,:])[np.newaxis,np.newaxis,:],Nbeams,axis=0),Nlags,axis=1)
    S['Acf']['Psc']=S['Acf']['Pulsewidth']*Ksys/(Range*Range)
    
    # Clutter to Noise ratio
    S['Acf']['iSCR'] = (Nbauds-1.0)*np.ones(Nlags)
    S['Power']['iSCR'] = 0.0
    
    # if uselag1=1, use the 1st lag to compute the apriori density
    if uselag1:
        # S['Power']['Data']=np.real(S['Acf']['Data'][:,S['Acf']['Lag1Index'],:])
        # S['Power']['StDev']=S['Acf']['StDev']
        # S['Power']['PulsesIntegrated']=S['Acf']['PulsesIntegrated'][:,S['Acf']['Lag1Index'],:]
        # S['Power']['Pulsewidth']=S['Acf']['Pulsewidth']
        # S['Power']['TxBaud']=S['Acf']['TxBaud']
        # S['Power']['Range']=S['Acf']['Range']
        # S['Acf']['Kint'][1:]=S['Acf']['Kint'][1:]*(Nbauds-1.0)**2.0
        # S['Acf']['Kint'][0]=S['Acf']['Kint'][0]*(Nbauds*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))**2.0
        # S['Power']['SNR']=np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/((Nbauds-1.0)*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))
        # #S['Power']['SNR']=np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/(np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))
        # S['Power']['iSCR']=Nbauds-1.0
        # #S['Power']['Kint']=Nbauds-1.0
        # S['Power']['Kint']=S['Acf']['Kint'][S['Acf']['Lag1Index']]


        S['Power']['Data'] = np.real(S['Acf']['Data'][:,S['Acf']['Lag1Index'],:])
        S['Power']['StDev'] = S['Acf']['StDev']
        S['Power']['PulsesIntegrated'] = S['Acf']['PulsesIntegrated'][:,S['Acf']['Lag1Index'],:]
        S['Power']['Pulsewidth'] = S['Acf']['Pulsewidth']
        S['Power']['TxBaud'] = S['Acf']['TxBaud']
        S['Power']['Range'] = S['Acf']['Range']
        # S['Acf']['Kint'][1:] = S['Acf']['Kint'][1:]*(Nbauds-1.0)**2.0
        S['Acf']['Kint'][0] = S['Acf']['Kint'][0]*(Nbauds*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))**2.0
        S['Power']['SNR'] = np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/((Nbauds-1.0)*np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))
        #S['Power']['SNR']=np.absolute(S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/(np.sum(np.squeeze(Amb['Wlag'][S['Acf']['Lag1Index'],:])))
        S['Power']['iSCR'] = Nbauds-1.0
        #S['Power']['Kint']=Nbauds-1.0
        S['Power']['Kint'] = S['Acf']['Kint'][S['Acf']['Lag1Index']]

    else:
        # set the 0 lag of the ACF to the short pulse zerolag measurement
        S['Acf']['Data'][:,0,:] = S['Power']['Data']
        S['Acf']['Psc'][:,0,:] = S['Acf']['Psc'][:,0,:]*S['Power']['Pulsewidth']/S['Acf']['Pulsewidth']
        S['Acf']['Kint'][0]=1.0
        # S['Acf']['Kint'][1:]=S['Acf']['Kint'][1:]*(Nbauds-1.0)**2.0
        S['Acf']['iSCR'][0]=0.0

    return S,N,C


def process_altcode_multifreq(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None,h5PwrPath='/S/ZeroLags'):
    
    Nfreqs=len(fconts)
    for ii in range(Nfreqs):
        if len(Irecs[ii])>0:
            tS,tN,tC=process_altcode(fconts[ii],Irecs[ii],acfopts,Amb,doamb=doamb,extCal=extCal,h5DataPath=h5DataPath,BeamCodes=BeamCodes,h5PwrPath='/S/ZeroLags')
            BeamCodes=tS['BMCODES']
            if ii==0:
                S=tS.copy(); N=tN.copy(); C=tC.copy()
                # ACF                
                if acfopts['DO_FITS']:
                    acfIntsS = tS['Acf']['PulsesIntegrated']
                    S['Acf']['Data']=tS['Acf']['Data']*acfIntsS
                    S['Acf']['Psc']=tS['Acf']['Psc']*acfIntsS
                    ind = np.where(~np.isfinite(S['Acf']['Data']))
                    S['Acf']['Data'][ind] = 0.0 + 0.0j
                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                S['Power']['Data']=tS['Power']['Data']*pwrIntsS
                N['Power']['Data']=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                S['Power']['SNR']=tS['Power']['SNR']*pwrIntsS
                S['Power']['StDev']=tS['Power']['StDev']*pwrIntsS
                ind = np.where(~np.isfinite(S['Power']['Data']))
                S['Power']['Data'][ind] = 0
                ind = np.where(~np.isfinite(S['Power']['SNR']))
                S['Power']['SNR'][ind] = 0
                # Pulses Integrated
                S['Power']['PulsesIntegrated']=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']=tC['Power']['PulsesIntegrated']                
                if acfopts['DO_FITS']:
                    S['Acf']['PulsesIntegrated']=tS['Acf']['PulsesIntegrated']
            else:
                # ACF                
                if acfopts['DO_FITS']:
                    acfIntsS = tS['Acf']['PulsesIntegrated']
                    ind = np.where(np.isfinite(tS['Acf']['Data']))
                    S['Acf']['Data'][ind]+=tS['Acf']['Data'][ind]*acfIntsS[ind]
                    S['Acf']['Psc']+=tS['Acf']['Psc']*acfIntsS
                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                ind = np.where(np.isfinite(tS['Power']['Data']))
                S['Power']['Data'][ind]+=tS['Power']['Data'][ind]*pwrIntsS[ind]
                N['Power']['Data']+=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']+=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                ind = np.where(np.isfinite(tS['Power']['SNR']))
                S['Power']['SNR'][ind]+=tS['Power']['SNR'][ind]*pwrIntsS[ind]
                S['Power']['StDev']+=tS['Power']['StDev']*pwrIntsS
                # Pulses Integrated
                S['Power']['PulsesIntegrated']+=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']+=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']+=tC['Power']['PulsesIntegrated']                
                if acfopts['DO_FITS']:
                    S['Acf']['PulsesIntegrated']+=tS['Acf']['PulsesIntegrated']

    # ACF
    if acfopts['DO_FITS']:    
        acfIntsS = S['Acf']['PulsesIntegrated']
        S['Acf']['Data']/=acfIntsS
        S['Acf']['Psc']/=acfIntsS
    # Power
    pwrIntsS = S['Power']['PulsesIntegrated']
    S['Power']['Data']/=pwrIntsS
    N['Power']['Data']/=N['Power']['PulsesIntegrated']
    C['Power']['Data']/=C['Power']['PulsesIntegrated']
    S['Power']['SNR']/=pwrIntsS
    S['Power']['StDev']/=pwrIntsS
    
    return S,N,C

def process_longpulse(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath=None,BeamCodes=None):
    
    funcname='np.nanmean'
    if acfopts['procMedian']==1:
        funcname='complex_median'

    if extCal==1:
        try:
            fcontsCal=fconts[1]
            fconts=fconts[0]
        except:
            print('External cal problem')

    if h5DataPath is None:
        h5DataPath = '/S/Data'
     
    # initialize signal 
    S={} 
    S['Acf']={}
    S['Power']={}

    # initialize noise 
    N={}
    N['Acf']={}
    N['Power']={}

    # initialize cal 
    C={}
    C['Power']={}
    C['Pcal']=fconts['/Rx']['Bandwidth']*fconts['/Rx']['CalTemp']*v_Boltzmann # Cal power in Watts

    # some generic stuff
    try:
        S['Power']['Pulsewidth']=fconts[h5DataPath]['Pulsewidth']
        S['Power']['TxBaud']=fconts[h5DataPath]['TxBaud']
        S['Acf']['Pulsewidth']=fconts[h5DataPath]['Pulsewidth']
        S['Acf']['TxBaud']=fconts[h5DataPath]['TxBaud']
    except: # to handle older data where PW and TXBAUD weren't recorded
        S['Power']['Pulsewidth']=acfopts['DEFOPTS']['PW_DEF']
        S['Power']['TxBaud']=acfopts['DEFOPTS']['TXBAUD_DEF']
        S['Acf']['Pulsewidth']=acfopts['DEFOPTS']['PW_DEF']
        S['Acf']['TxBaud']=acfopts['DEFOPTS']['TXBAUD_DEF']

    # Antenna if necessary
    if acfopts['MOTION_TYPE']==1:   
        az=fconts['/Antenna']['Azimuth'][Irecs]
        el=fconts['/Antenna']['Elevation'][Irecs]
        I=np.where(el>90.0)[0]; el[I]=180.0-el[I]; az[I]=az[I]+180.0
        I=np.where(az>360.0)[0]; az[I]=az[I]-360.0
        I=np.where(az<0.0)[0]; az[I]=az[I]+360.0
        S['AvgAzimuth']=azAverage(az*pi/180.0)*180.0/pi
        S['AvgElevation']=np.mean(el)
        S['Azimuth']=np.array([az[0,0],az[-1,-1]])
        S['Elevation']=np.array([el[0,0],el[-1,-1]])
                
    # ACF
    S['Acf']['Data']=fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,:,0].astype(complex)
    S['Acf']['Data'].imag=fconts[h5DataPath+'/Acf']['Data'][Irecs,:,:,:,1]
    N['Acf']['Data']=fconts['/S/Noise/Acf']['Data'][Irecs,:,:,:,0].astype(complex)
    N['Acf']['Data'].imag=fconts['/S/Noise/Acf']['Data'][Irecs,:,:,:,1]
    (Nrecs,Nbeams,Nlags,Nranges)=S['Acf']['Data'].shape; NbeamsIn=Nbeams
    S['Acf']['Range']=fconts[h5DataPath+'/Acf']['Range'][[0]];
    S['Acf']['Lags']=fconts[h5DataPath+'/Acf']['Lags']
    S['Acf']['Kint']=np.ones(Nlags,dtype=float)
    S['Acf']['iSCR']=np.zeros(Nlags,dtype=float)


    input_power = fconts[h5DataPath+'/Power']['Data'][Irecs,:,:]
    input_noise = fconts['/S/Noise/Power']['Data'][Irecs,:,:]
    noise_Nranges = input_noise.shape[2]


    # Determine the existence and dimensionality of the pulses integrated arrays
    # (implemented by ASR to handle resampled data 15/03/2017)

    # ACF pulses integrated
    try:
        acf_pulses_integrated = fconts[h5DataPath+'/Acf']['PulsesIntegrated']
    except KeyError:
        acf_pulses_integrated = fconts[h5DataPath]['PulsesIntegrated']
    if np.ndim(acf_pulses_integrated) == 2:
        acf_pulses_integrated = np.repeat(acf_pulses_integrated[:,:,np.newaxis],Nlags,axis=2)
    if np.ndim(acf_pulses_integrated) == 3:
        acf_pulses_integrated = np.repeat(acf_pulses_integrated[:,:,:,np.newaxis],Nranges,axis=3)
    acf_pulses_integrated = acf_pulses_integrated[Irecs,:,:,:]


    # Noise ACF pulses integrated
    try:
        noise_noise_acf_pulses_integrated = fconts['/S/Noise/Acf']['PulsesIntegrated']
    except KeyError:
        noise_acf_pulses_integrated = fconts['/S/Noise']['PulsesIntegrated']
    if np.ndim(noise_acf_pulses_integrated) == 2:
        noise_acf_pulses_integrated = np.repeat(noise_acf_pulses_integrated[:,:,np.newaxis],Nlags,axis=2)
    if np.ndim(noise_acf_pulses_integrated) == 3:
        noise_acf_pulses_integrated = np.repeat(noise_acf_pulses_integrated[:,:,:,np.newaxis],noise_Nranges,axis=3)
    noise_acf_pulses_integrated = noise_acf_pulses_integrated[Irecs,:,:,:]


    # Power pulses integrated
    try:
        power_pulses_integrated = fconts[h5DataPath+'/Power']['PulsesIntegrated']
    except KeyError:
        power_pulses_integrated = fconts[h5DataPath]['PulsesIntegrated']
    if np.ndim(power_pulses_integrated) == 2:
        power_pulses_integrated = np.repeat(power_pulses_integrated[:,:,np.newaxis],Nranges,axis=2)
    power_pulses_integrated = power_pulses_integrated[Irecs,:,:]

    # Noise pulses integrated
    try:
        noise_power_pulses_integrated = fconts['/S/Noise/Power']['PulsesIntegrated']
    except KeyError:
        noise_power_pulses_integrated = fconts['/S/Noise']['PulsesIntegrated']
    if np.ndim(noise_power_pulses_integrated) == 2:
        noise_power_pulses_integrated = np.repeat(noise_power_pulses_integrated[:,:,np.newaxis],noise_Nranges,axis=2)
    noise_power_pulses_integrated = noise_power_pulses_integrated[Irecs,:,:]


    # Anywhere that our ACFs or Powers pulses integrated is 0, we must make sure the data is zeroed out too
    S['Acf']['Data'][np.where(acf_pulses_integrated == 0)] = 0.0+0.0j
    N['Acf']['Data'][np.where(noise_acf_pulses_integrated == 0)] = 0.0+0.0j
    input_power[np.where(power_pulses_integrated == 0)] = 0
    input_noise[np.where(noise_power_pulses_integrated == 0)] = 0

    # Now let's test if the noise estimates are "good enough" or should be replaced
    # by comparing the noise estimates against furthest ranges of data
    input_power_pulses_integrated = power_pulses_integrated
    input_noise_power_pulses_integrated = noise_power_pulses_integrated

    output_noise, output_noise_pulses_integrated = check_noise(input_noise, input_power,
                                                               input_noise_power_pulses_integrated,
                                                               input_power_pulses_integrated)

    # Power
    S['Power']['Data']  = input_power
    N['Power']['Data']  = output_noise
    S['Power']['Range'] = fconts[h5DataPath+'/Power']['Range'][[0]]; 
    if extCal==0:
        C['Power']['Data']      = fconts['/S/Cal/Power']['Data'][Irecs,:,:]
    elif extCal==1:
        C['Power']['Data']      = fcontsCal['/S/Cal/Power']['Data'][Irecs,:,:]
        C['Power']['NoiseData'] = fcontsCal['/S/Noise/Power']['Data'][Irecs,:,:]
    S['Power']['Kint']=1.0
    S['Power']['iSCR']=0.0
        
    # Pulses Integrated
    S['Power']['PulsesIntegrated']  = input_power_pulses_integrated
    N['Power']['PulsesIntegrated']  = output_noise_pulses_integrated
    S['Acf']['PulsesIntegrated']    = acf_pulses_integrated
    N['Acf']['PulsesIntegrated']    = noise_acf_pulses_integrated
    if extCal==0 or extCal==2:
        C['Power']['PulsesIntegrated']=fconts['/S/Cal']['PulsesIntegrated'][Irecs,:]
    elif extCal==1:
        C['Power']['PulsesIntegrated']=fcontsCal['/S/Cal']['PulsesIntegrated'][Irecs,:]
        C['Power']['NoisePulsesIntegrated']=fcontsCal['/S/Noise']['PulsesIntegrated'][Irecs,:]        

    # Beamcodes
    S['Power']['Beamcodes']=fconts[h5DataPath]['Beamcodes'][Irecs,:]
    S['Acf']['Beamcodes']=fconts[h5DataPath]['Beamcodes'][Irecs,:]
    N['Power']['Beamcodes']=fconts['/S/Noise']['Beamcodes'][Irecs,:]
    N['Acf']['Beamcodes']=fconts['/S/Noise']['Beamcodes'][Irecs,:]
    if extCal==0:
        C['Power']['Beamcodes']=fconts['/S/Cal']['Beamcodes'][Irecs,:]
    elif extCal==1:
        C['Power']['Beamcodes']=fcontsCal['/S/Cal']['Beamcodes'][Irecs,:]
        C['Power']['NoiseBeamcodes']=fcontsCal['/S/Noise']['Beamcodes'][Irecs,:]
    
    # Ambiguity function path
    if doamb:
        # try:
        S['Power']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts['/S/Data']['Ambiguity'])])
        S['Acf']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts['/S/Data']['Ambiguity'])])
        # for the power, we are dealing only with the zero lags
        S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][0,:] 
        S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][0,:] 
        # except:
        #     print('Unable to load ambiguity function')
                
    if acfopts['MOTION_TYPE']==0:
        # Deal the data
        beamcodes=np.sort(S['Acf']['Beamcodes'][0,:])
        # signal
        S['Power']['Data']=deal_data(S['Power']['Beamcodes'],S['Power']['Data'],beamcodes)
        S['Acf']['Data']=deal_data(S['Acf']['Beamcodes'],S['Acf']['Data'],beamcodes)
        S['Power']['PulsesIntegrated']=deal_data(S['Power']['Beamcodes'],S['Power']['PulsesIntegrated'],beamcodes)
        S['Acf']['PulsesIntegrated']=deal_data(S['Acf']['Beamcodes'],S['Acf']['PulsesIntegrated'],beamcodes)
        # noise
        N['Power']['Data']=deal_data(N['Power']['Beamcodes'],N['Power']['Data'],beamcodes)
        N['Acf']['Data']=deal_data(N['Acf']['Beamcodes'],N['Acf']['Data'],beamcodes)
        N['Power']['PulsesIntegrated']=deal_data(N['Power']['Beamcodes'],N['Power']['PulsesIntegrated'],beamcodes)  
        N['Acf']['PulsesIntegrated']=deal_data(N['Acf']['Beamcodes'],N['Acf']['PulsesIntegrated'],beamcodes)    
        # cal
        if extCal!=2:
            C['Power']['Data']=deal_data(C['Power']['Beamcodes'],C['Power']['Data'],beamcodes)
            C['Power']['PulsesIntegrated']=deal_data(C['Power']['Beamcodes'],C['Power']['PulsesIntegrated'],beamcodes)  
        if extCal==1:
            C['Power']['NoiseData']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoiseData'],beamcodes)
            C['Power']['NoisePulsesIntegrated']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoisePulsesIntegrated'],beamcodes)  
        
        # get the beamcodes
        if BeamCodes is None:
            if np.sum(fconts['/Setup']['BeamcodeMap'][:,3])==0.0:
                try:
                    f=open(acfopts['DEFOPTS']['BMCODEMAP_DEF'])
                    fconts['/Setup']['BeamcodeMap']=np.loadtxt(f)
                    f.close()
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['DEFOPTS']['BMCODEMAP_DEF'])
            S['BMCODES']=np.zeros((Nbeams,4),dtype=float)-1 # beamcode table (beamcode,az,el,ksys)
            for i in range(Nbeams):
                I=np.where(fconts['/Setup']['BeamcodeMap'][:,0]==beamcodes[i])[0]
                S['BMCODES'][i,:]=fconts['/Setup']['BeamcodeMap'][I,:]
                if S['BMCODES'][i,3]==0.0:
                    print('Using default system constant, %4.4e' % (acfopts['DEFOPTS']['KSYS_DEF']))
                    S['BMCODES'][i,3]=acfopts['DEFOPTS']['KSYS_DEF']
            if acfopts['beamMapScale']:
                try:
                    f=open(acfopts['beamMapScaleFile'])
                    BmScaler=np.loadtxt(f)
                    f.close()
                    print('Using Beam Code scaler from %s' % acfopts['beamMapScaleFile'] )
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['beamMapScaleFile'])
                for i in range(Nbeams):
                    I=np.where(BmScaler[:,0]==beamcodes[i])[0]
                    
                    if len(I)>0:
                        # replace
                        
                        S['BMCODES'][i,3]=BmScaler[I,3]
                    else:
                        raise IOError('No Beam %d in %s!' % (beamcodes[i], acfopts['beamMapScaleFile']))
        else:
            S['BMCODES']=BeamCodes
            NbeamsIn = BeamCodes.shape[0]
        Ksys=np.repeat(np.repeat(S['BMCODES'][:,3][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)
        
    elif acfopts['MOTION_TYPE']==1:
        try:
            S['Ksys']=fconts['/Rx']['SysConst']
        except KeyError:
            print("/Rx/SysConst not found, using hardcoded default: %s" % str(S['Ksys']))
            S['Ksys']=acfopts['DEFOPTS']['KSYS_DEF']
        Ksys=S['Ksys']
        S['BMCODES']=np.array([[-1,S['AvgAzimuth'],S['AvgElevation'],Ksys]])
                                
    # Average the noise and cal power samples
    N['Power']['Data']=np.nanmean(complex_median(N['Power']['Data']/N['Power']['PulsesIntegrated'],axis=2),axis=0)
    N['Acf']['Data']=np.nanmean(complex_median(N['Acf']['Data']/N['Acf']['PulsesIntegrated'],axis=3),axis=0)
    if extCal!=2:
        C['Power']['Data']=np.mean(complex_median(C['Power']['Data'],axis=2)/C['Power']['PulsesIntegrated'],axis=0)
    if extCal==0:
        C['Power']['Data']=C['Power']['Data']-N['Power']['Data']
    elif extCal==1:
        C['Power']['NoiseData']=np.nanmean(complex_median(C['Power']['NoiseData'],axis=2)/C['Power']['NoisePulsesIntegrated'],axis=0)
        C['Power']['Data']=C['Power']['Data']-C['Power']['NoiseData']
        C['Power']['Data']=(C['Power']['Data']/C['Power']['NoiseData'])*N['Power']['Data'] # (C/Ncal)*N
    elif extCal==2:
        C['Power']['Data']=N['Power']['Data']*acfopts['CalToNoiseRatio']

    if extCal!=2:
        C['Power']['PulsesIntegrated']=np.sum(C['Power']['PulsesIntegrated'],axis=0) # total number of pulses used for the estimate


    # convert noise to Watts
    N['Power']['Data']=C['Pcal']*(N['Power']['Data']/C['Power']['Data']) # Noise Power in Watts
    N['Power']['PulsesIntegrated']=np.sum(np.sum(N['Power']['PulsesIntegrated'],axis=2),axis=0) # total number of pulses used for the estimate

    N['Acf']['Data']=C['Pcal']*N['Acf']['Data']/np.repeat(np.reshape(C['Power']['Data'],(Nbeams,1)),Nlags,axis=1) # Noise Acf in Watts
    N['Acf']['PulsesIntegrated']=np.sum(np.sum(N['Acf']['PulsesIntegrated'],axis=3),axis=0) # total number of pulses used for the estimate

    # Convert power data and power ACF to Watts
    S['Power']['Data']=S['Power']['Data']/S['Power']['PulsesIntegrated']
    S['Power']['PulsesIntegrated']=np.sum(S['Power']['PulsesIntegrated'],axis=0) # total number of pulses used for the estimate
    S['Power']['StDev']=np.std(S['Power']['Data'],axis=0)/np.sqrt(Nrecs)
    S['Power']['Data']=eval(funcname+"(S['Power']['Data'],axis=0)")
    S['Power']['StDev']=S['Power']['StDev']/S['Power']['Data']


    # SNR = S/N, we subtract off the average noise, then fit the data with a data model + perturbation noise model
    S['Power']['Data']  = C['Pcal']*S['Power']['Data']/np.repeat(C['Power']['Data'][:,np.newaxis],Nranges,axis=1)
    S['Power']['Data']  = S['Power']['Data'] - np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1)
    S['Power']['SNR']   = S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1)

    if acfopts['DO_FITS']:
        S['Acf']['Data']=S['Acf']['Data']/S['Acf']['PulsesIntegrated']
        S['Acf']['PulsesIntegrated']=np.sum(S['Acf']['PulsesIntegrated'],axis=0) # total number of pulses used for the estimate 
        S['Acf']['Data']=eval(funcname+"(S['Acf']['Data'],axis=0)")
        # calibrate the ACF data and then subtract off the noise ACF
        S['Acf']['Data']=C['Pcal']*S['Acf']['Data']/np.repeat(np.repeat(C['Power']['Data'][:,np.newaxis,np.newaxis],Nlags,axis=1),Nranges,axis=2)
        S['Acf']['Data']=S['Acf']['Data']-np.repeat(N['Acf']['Data'][:,:,np.newaxis],Nranges,axis=2)

    Range=np.repeat(np.repeat(np.squeeze(S['Acf']['Range'])[np.newaxis,np.newaxis,:],NbeamsIn,axis=0),Nlags,axis=1)
    S['Acf']['Psc']=S['Acf']['Pulsewidth']*Ksys/(Range*Range)

    return S,N,C

    
def process_longpulse_multifreq(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None):
    
    Nfreqs=len(fconts)
    for ii in range(Nfreqs):
        if len(Irecs[ii])>0:
            tS,tN,tC=process_longpulse(fconts[ii],Irecs[ii],acfopts,Amb,doamb=doamb,extCal=extCal,h5DataPath=h5DataPath,BeamCodes=BeamCodes)
            BeamCodes=tS['BMCODES']
            if ii==0:
                S=tS.copy(); N=tN.copy(); C=tC.copy()
                # ACF                
                if acfopts['DO_FITS']:
                    acfIntsS = tS['Acf']['PulsesIntegrated']
                    acfIntsN = tN['Acf']['PulsesIntegrated']
                    S['Acf']['Data']=tS['Acf']['Data']*acfIntsS
                    N['Acf']['Data']=tN['Acf']['Data']*acfIntsN
                    S['Acf']['Psc']=tS['Acf']['Psc']*acfIntsS
                    ind = np.where(~np.isfinite(S['Acf']['Data']))
                    S['Acf']['Data'][ind] = 0.0 + 0.0j

                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                S['Power']['Data']=tS['Power']['Data']*pwrIntsS
                N['Power']['Data']=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                S['Power']['SNR']=tS['Power']['SNR']*pwrIntsS
                S['Power']['StDev']=tS['Power']['StDev']*pwrIntsS
                ind = np.where(~np.isfinite(S['Power']['Data']))
                S['Power']['Data'][ind] = 0.0
                ind = np.where(~np.isfinite(S['Power']['SNR']))
                S['Power']['SNR'][ind] = 0.0
                # Pulses Integrated
                S['Power']['PulsesIntegrated']=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']=tC['Power']['PulsesIntegrated']                
                if acfopts['DO_FITS']:
                    S['Acf']['PulsesIntegrated']=tS['Acf']['PulsesIntegrated']
                    N['Acf']['PulsesIntegrated']=tN['Acf']['PulsesIntegrated']
            else:
                # ACF                
                if acfopts['DO_FITS']:
                    acfIntsS = tS['Acf']['PulsesIntegrated']
                    acfIntsN = tN['Acf']['PulsesIntegrated']
                    ind = np.where(np.isfinite(tS['Acf']['Data']))
                    S['Acf']['Data'][ind]+=tS['Acf']['Data'][ind]*acfIntsS[ind]
                    N['Acf']['Data']+=tN['Acf']['Data']*acfIntsN
                    S['Acf']['Psc']+=tS['Acf']['Psc']*acfIntsS
                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                ind = np.where(np.isfinite(tS['Power']['Data']))
                S['Power']['Data'][ind]+=tS['Power']['Data'][ind]*pwrIntsS[ind]
                N['Power']['Data']+=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']+=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                ind = np.where(np.isfinite(tS['Power']['SNR']))
                S['Power']['SNR'][ind]+=tS['Power']['SNR'][ind]*pwrIntsS[ind]
                S['Power']['StDev']+=tS['Power']['StDev']*pwrIntsS
                # Pulses Integrated
                S['Power']['PulsesIntegrated']+=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']+=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']+=tC['Power']['PulsesIntegrated']                
                if acfopts['DO_FITS']:
                    S['Acf']['PulsesIntegrated']+=tS['Acf']['PulsesIntegrated']
                    N['Acf']['PulsesIntegrated']+=tN['Acf']['PulsesIntegrated']

    # ACF
    if acfopts['DO_FITS']:    
        acfIntsS = S['Acf']['PulsesIntegrated']
        acfIntsN = N['Acf']['PulsesIntegrated']
        S['Acf']['Data']/=acfIntsS
        N['Acf']['Data']/=acfIntsN
        S['Acf']['Psc']/=acfIntsS
    # Power
    pwrIntsS = S['Power']['PulsesIntegrated']
    S['Power']['Data']/=pwrIntsS
    N['Power']['Data']/=N['Power']['PulsesIntegrated']
    C['Power']['Data']/=C['Power']['PulsesIntegrated']
    S['Power']['SNR']/=pwrIntsS
    S['Power']['StDev']/=pwrIntsS
    
    return S,N,C

def process_barkercode(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None):
                
    funcname='np.nanmean'
    if acfopts['procMedian']==1:
        funcname='complex_median'
        
    if fconts.has_key('/CohCode/Data'):
        gname='/CohCode/Data'
    elif fconts.has_key('/CohCode/ZeroLags'):
        gname='/CohCode/ZeroLags'
    else:
         raise IOError('Cannot find data group in file')

    # initialize signal 
    S={} 
    S['Power']={}


    # Ambiguity function path
    if doamb:
        S['Power']['Ambiguity']=io_utils.copyAmbDict(fconts[str(fconts[gname]['Ambiguity'])])
        # Check for Bandwidth in Ambiguity function. If not there, throw exception
        if not'Bandwidth' in S['Power']['Ambiguity'].keys():
            raise KeyError('No Bandwidth found in the ambiguity function file! This is needed to calibrate Barker Code electron densities.')
        # for the power, we are dealing only with the zero lags
        S['Power']['Ambiguity']['Wlag']=S['Power']['Ambiguity']['Wlag'][0,:][np.newaxis,:]
        S['Power']['Ambiguity']['Wrange']=S['Power']['Ambiguity']['Wrange'][0,:][np.newaxis,:]
    else:
        S['Power']['Ambiguity']=Amb

    # initialize noise 
    N={}
    N['Power']={}

    # initialize cal 
    C={}
    C['Power']={}
    C['Pcal']=fconts['/Rx']['Bandwidth']*fconts['/Rx']['CalTemp']*v_Boltzmann # Cal power in Watts
    C['Pcal']=C['Pcal']/fconts['/Rx']['Bandwidth']*S['Power']['Ambiguity']['Bandwidth'] # adjust for BC bandwidth.

    # Antenna if necessary
    if acfopts['MOTION_TYPE']==1:   
        az=fconts['/Antenna']['Azimuth'][Irecs]
        el=fconts['/Antenna']['Elevation'][Irecs]
        I=np.where(el>90.0)[0]; el[I]=180.0-el[I]; az[I]=az[I]+180.0
        I=np.where(az>360.0)[0]; az[I]=az[I]-360.0
        I=np.where(az<0.0)[0]; az[I]=az[I]+360.0
        S['AvgAzimuth']=azAverage(az*pi/180.0)*180.0/pi
        S['AvgElevation']=np.mean(el)
        S['Azimuth']=np.array([az[0,0],az[-1,-1]])
        S['Elevation']=np.array([el[0,0],el[-1,-1]])

    # some generic stuff
    S['Power']['Pulsewidth']=fconts[gname]['Pulsewidth']
    S['Power']['TxBaud']=fconts[gname]['TxBaud']
    

    # Now let's test if the noise estimates are "good enough" or should be replaced
    # by comparing the noise estimates against furthest ranges of data
    input_power = fconts[gname+'/Power']['Data'][Irecs,:,:]
    input_noise = fconts['/CohCode/Noise/Power']['Data'][Irecs,:,:]
    (Nrecs,Nbeams,Nranges) = input_power.shape
    (_,_,noise_Nranges) = input_noise.shape

    # Determine the existence and dimensionality of the pulses integrated arrays
    # (implemented by ASR to handle resampled data 15/03/2017)

    # Power pulses integrated
    power_pulses_integrated = fconts[gname]['PulsesIntegrated']
    if np.ndim(power_pulses_integrated) == 2:
        power_pulses_integrated = np.repeat(power_pulses_integrated[:,:,np.newaxis],Nranges,axis=2)
    input_power_pulses_integrated = power_pulses_integrated[Irecs,:,:]

    # Noise pulses integrated
    noise_power_pulses_integrated = fconts['/CohCode/Noise']['PulsesIntegrated']
    if np.ndim(noise_power_pulses_integrated) == 2:
        noise_power_pulses_integrated = np.repeat(noise_power_pulses_integrated[:,:,np.newaxis],noise_Nranges,axis=2)
    input_noise_pulses_integrated = noise_power_pulses_integrated[Irecs,:,:]


    output_noise, output_noise_pulses_integrated = check_noise(input_noise, input_power,
                                                               input_noise_pulses_integrated,
                                                               input_power_pulses_integrated)

    # Power
    S['Power']['Data']  = input_power
    N['Power']['Data']  = output_noise
    C['Power']['Data']  = fconts['/CohCode/Cal/Power']['Data'][Irecs,:,:]
    S['Power']['Range'] = fconts[gname+'/Power']['Range'][[0]]; 
    (Nrecs,Nbeams,Nranges) = S['Power']['Data'].shape
    S['Power']['Kint']=1.0
    S['Power']['iSCR']=0.0  

    # Pulses Integrated
    S['Power']['PulsesIntegrated']  = input_power_pulses_integrated
    N['Power']['PulsesIntegrated']  = output_noise_pulses_integrated
    C['Power']['PulsesIntegrated']  = fconts['/CohCode/Cal']['PulsesIntegrated'][Irecs,:]

    # Beamcodes
    S['Power']['Beamcodes']=fconts[gname]['Beamcodes'][Irecs,:]
    N['Power']['Beamcodes']=fconts['/CohCode/Noise']['Beamcodes'][Irecs,:]
    C['Power']['Beamcodes']=fconts['/CohCode/Cal']['Beamcodes'][Irecs,:]

    if acfopts['MOTION_TYPE']==0:
        # Deal the data
        beamcodes=np.sort(S['Power']['Beamcodes'][0,:])
        # signal
        S['Power']['Data']=deal_data(S['Power']['Beamcodes'],S['Power']['Data'],beamcodes)
        S['Power']['PulsesIntegrated']=deal_data(S['Power']['Beamcodes'],S['Power']['PulsesIntegrated'],beamcodes)
        # noise
        N['Power']['Data']=deal_data(N['Power']['Beamcodes'],N['Power']['Data'],beamcodes)
        N['Power']['PulsesIntegrated']=deal_data(N['Power']['Beamcodes'],N['Power']['PulsesIntegrated'],beamcodes)  
        # cal
        if extCal!=2:
            C['Power']['Data']=deal_data(C['Power']['Beamcodes'],C['Power']['Data'],beamcodes)
            C['Power']['PulsesIntegrated']=deal_data(C['Power']['Beamcodes'],C['Power']['PulsesIntegrated'],beamcodes)  
        if extCal==1:
            C['Power']['NoiseData']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoiseData'],beamcodes)
            C['Power']['NoisePulsesIntegrated']=deal_data(C['Power']['NoiseBeamcodes'],C['Power']['NoisePulsesIntegrated'],beamcodes)      
        
        # get the beamcodes
        if BeamCodes is None:
            a=fconts['/Setup']['BeamcodeMap']
            #print(fconts['/Setup'])
            #print(fconts['/Setup']['BeamcodeMap'][:,3])
            if np.sum(fconts['/Setup']['BeamcodeMap'][:,3])==0.0:
                try:
                    f=open(acfopts['DEFOPTS']['BMCODEMAP_DEF'])
                    fconts['/Setup']['BeamcodeMap']=np.loadtxt(f)
                    f.close()
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['DEFOPTS']['BMCODEMAP_DEF'])
            S['BMCODES']=np.zeros((Nbeams,4),dtype=float)-1 # beamcode table (beamcode,az,el,ksys)
            for i in range(Nbeams):
                I=np.where(fconts['/Setup']['BeamcodeMap'][:,0]==beamcodes[i])[0]
                S['BMCODES'][i,:]=fconts['/Setup']['BeamcodeMap'][I,:]
                if S['BMCODES'][i,3]==0.0:
                    print('Using default system constant, %4.4e' % (acfopts['DEFOPTS']['KSYS_DEF']))
                    S['BMCODES'][i,3]=acfopts['DEFOPTS']['KSYS_DEF']
            if acfopts['beamMapScale']:
                try:
                    f=open(acfopts['beamMapScaleFile'])
                    BmScaler=np.loadtxt(f)
                    f.close()
                    print('Using Beam Code scaler from %s' % acfopts['beamMapScaleFile'] )
                except:
                    raise IOError('BeamCode error: Could not read %s' % acfopts['beamMapScaleFile'])
                for i in range(Nbeams):
                    I=np.where(BmScaler[:,0]==beamcodes[i])[0]
                    if len(I)>0:
                        # replace
                        S['BMCODES'][i,3]=BmScaler[I,3]
                    else:
                        raise IOError('No Beam %d in %s!' % (beamcodes[i], acfopts['beamMapScaleFile']))
        else:
            S['BMCODES']=BeamCodes
        
    elif acfopts['MOTION_TYPE']==1:
        try:
            S['Ksys']=fconts['/Rx']['SysConst']
        except KeyError:
            print("/Rx/SysConst not found, using hardcoded default: %s" % str(S['Ksys']))
            S['Ksys']=acfopts['DEFOPTS']['KSYS_DEF']
        Ksys=S['Ksys']
        S['BMCODES']=np.array([[-1,S['AvgAzimuth'],S['AvgElevation'],Ksys]])
        
                                                
    # Average the noise and cal power samples
    N['Power']['Data']=np.nanmean(complex_median(N['Power']['Data']/N['Power']['PulsesIntegrated'],axis=2),axis=0)
    if extCal!=2:
        C['Power']['Data']=np.mean(complex_median(C['Power']['Data'],axis=2)/C['Power']['PulsesIntegrated'],axis=0)
    if extCal==0:
        C['Power']['Data']=C['Power']['Data']-N['Power']['Data']
    elif extCal==1:
        C['Power']['NoiseData']=np.nanmean(complex_median(C['Power']['NoiseData'],axis=2)/C['Power']['NoisePulsesIntegrated'],axis=0)
        C['Power']['Data']=C['Power']['Data']-C['Power']['NoiseData']
        C['Power']['Data']=(C['Power']['Data']/C['Power']['NoiseData'])*N['Power']['Data'] # (C/Ncal)*N
    elif extCal==2:
        C['Power']['Data']=N['Power']['Data']*acfopts['CalToNoiseRatio']
        
    # Noise subtract and calibrate power profle
    S['Power']['Data']=S['Power']['Data']/S['Power']['PulsesIntegrated']
    S['Power']['PulsesIntegrated']=np.sum(S['Power']['PulsesIntegrated'],axis=0) # total number of pulses used for the estimate
    N['Power']['PulsesIntegrated']=np.sum(np.sum(N['Power']['PulsesIntegrated'],axis=2),axis=0) # total number of pulses used for the estimate
    if extCal!=2:
        C['Power']['PulsesIntegrated']=np.sum(C['Power']['PulsesIntegrated'],axis=0) # total number of pulses used for the estimate
    S['Power']['StDev']=np.std(S['Power']['Data'],axis=0)/np.sqrt(Nrecs)
    S['Power']['Data']=eval(funcname+"(S['Power']['Data'],axis=0)")
    S['Power']['StDev']=S['Power']['StDev']/S['Power']['Data']
    S['Power']['Data']=C['Pcal']*(S['Power']['Data']-np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1))/np.repeat(C['Power']['Data'][:,np.newaxis],Nranges,axis=1)

    # convert noise to Watts
    N['Power']['Data']=C['Pcal']*(N['Power']['Data']/C['Power']['Data']) # Noise Power in Watts
                
    S['Power']['SNR']=S['Power']['Data']/np.repeat(N['Power']['Data'][:,np.newaxis],Nranges,axis=1)
    
    return S,N,C
    
def process_barkercode_multifreq(fconts,Irecs,acfopts,Amb,doamb=0,extCal=0,h5DataPath='',BeamCodes=None):
    
    Nfreqs=len(fconts)
    for ii in range(Nfreqs):
        if len(Irecs[ii])>0:
            tS,tN,tC=process_barkercode(fconts[ii],Irecs[ii],acfopts,Amb,doamb=doamb,extCal=extCal,h5DataPath=h5DataPath,BeamCodes=BeamCodes)
            print(tN['Power']['PulsesIntegrated'].shape)
            print(tN['Power']['Data'].shape)
            if ii==0:
                S=tS.copy(); N=tN.copy(); C=tC.copy()
                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                S['Power']['Data']=tS['Power']['Data']*pwrIntsS
                N['Power']['Data']=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                S['Power']['SNR']=tS['Power']['SNR']*pwrIntsS
                S['Power']['StDev']=tS['Power']['StDev']*pwrIntsS
                # Pulses Integrated
                S['Power']['PulsesIntegrated']=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']=tC['Power']['PulsesIntegrated']      
                
                BeamCodes=S['BMCODES']
            else:
                # Power
                pwrIntsS = tS['Power']['PulsesIntegrated']
                S['Power']['Data']+=tS['Power']['Data']*pwrIntsS
                N['Power']['Data']+=tN['Power']['Data']*tN['Power']['PulsesIntegrated']
                C['Power']['Data']+=tC['Power']['Data']*tC['Power']['PulsesIntegrated']
                S['Power']['SNR']+=tS['Power']['SNR']*pwrIntsS
                S['Power']['StDev']+=tS['Power']['StDev']*pwrIntsS
                # Pulses Integrated
                S['Power']['PulsesIntegrated']+=tS['Power']['PulsesIntegrated']
                N['Power']['PulsesIntegrated']+=tN['Power']['PulsesIntegrated']
                C['Power']['PulsesIntegrated']+=tC['Power']['PulsesIntegrated']     
            N['Power']['Data'].shape

    # Power
    pwrIntsS = S['Power']['PulsesIntegrated']
    S['Power']['Data']/=pwrIntsS
    N['Power']['Data']/=N['Power']['PulsesIntegrated']
    C['Power']['Data']/=C['Power']['PulsesIntegrated']
    S['Power']['SNR']/=pwrIntsS
    S['Power']['StDev']/=pwrIntsS
    
    return S,N,C
