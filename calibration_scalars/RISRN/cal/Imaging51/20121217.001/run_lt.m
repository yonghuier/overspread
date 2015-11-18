clear all;

exp='Imaging51';
files={
    '/Volumes/ISR_DATA_02/processed_data/RISR-N/2012/01/Imaging51/20120122.001/20120122.001_lp_2min.h5',
    '/Volumes/ISR_DATA_02/processed_data/RISR-N/2012/02/Imaging51/20120219.001/20120219.001_lp_2min.h5',
    };

Nfiles=length(files);

date=datestr(now,'mm.dd.yyyy');

Addit64157=0.31; %10/01/2012 based on initial CADI cal
AdditCode=60629; % 4 deg off boresight

altmin=200e3; altmax=350e3;
dm=60*60/6; % avg time
minNe=2e10;

for ifile=1:Nfiles
    fname=char(files(ifile)); dat=read_data(fname);
    fprintf('%s\n',fname);
    
   utime=dat.Time.UnixTime; utime2=mean(utime,1); dt=median(diff(utime2)); dx=ceil(dm/dt);
    
   BMCODES=dat.BeamCodes; Ib=find(BMCODES(1,:)==AdditCode); Nbeams=size(BMCODES,2);
   alt=dat.NeFromPower.Altitude;
   tmp=dat.NeFromPower.Ne_NoTr;
   tmp(isnan(tmp))=0; tmp(tmp<0)=0;
   
   ialtIb=find(alt(:,Ib)>=(altmin-50e3) & alt(:,Ib)<=(altmax+50e3)); ialtIb2=find(alt(ialtIb,Ib)>=(altmin) & alt(ialtIb,Ib)<=(altmax));
   tmpIb=medianfilter2d(squeeze(tmp(ialtIb,Ib,:)),[3 dx])/Addit64157;
   tmpIb(tmpIb<minNe)=nan;

   for ibm=1:Nbeams
       ialt=find(alt(:,ibm)>=(altmin-50e3) & alt(:,ibm)<=(altmax+50e3));
       tmp2=medianfilter2d(squeeze(tmp(ialt,ibm,:)),[3 dx]);      
       tmp2=interp1(alt(ialt,ibm),tmp2,alt(ialtIb,Ib),'linear');
       tmp2(tmp2<minNe)=nan; 
       sc=tmp2./tmpIb; sc=sc(ialtIb2,2:end-1); sc2=reshape(sc,[size(sc,1)*size(sc,2) 1]); 
       scm(ifile,ibm)=median(sc2(isfinite(sc2))); scstd(ifile,ibm)=std(sc2(isfinite(sc2)));%/sqrt(length(sc2(isfinite(sc2))));
       angBs(ibm)=get_BS_angle(BMCODES(2,ibm)*pi/180,BMCODES(3,ibm)*pi/180);
   end
   [Y,I] = sort(angBs);
   plot(scm(ifile,:),'k-'); hold on;

end

if size(scm,1)>1
    scmout=nanmedian(scm);
    dscmout=nanstd(scm)/sqrt(length(scm));
else
    scmout=scm;
    dscmout=scmout*nan;
end

oBMCODES=BMCODES; oBMCODES(end,:)=oBMCODES(end,:).*scmout;
fid=fopen([exp '-calibration-' 'scalar' '-' date '.txt'],'w');
fid1=fopen([exp '-calibration-' 'ksys' '-' date '.txt'],'w');
for i=1:Nbeams
        fprintf(fid,'%d %2.2f %2.2f %2.2e %3.5f %3.5f\n',[BMCODES(:,i); scmout(i); dscmout(i)]);
        fprintf(fid1,'%d %2.2f %2.2f %2.2e\n',oBMCODES(:,i));
end
fclose(fid);
fclose(fid1);

errorbar(1:Nbeams,scmout,dscmout,dscmout,'k.'); hold on;

