import pandas as pd
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from utils.constants import dmgTypes,baseInfusions,infusionOrder,idWeaponClass,weaponClasses,infusionOffset,forbiddenAshBuff,rareBuff,ashBuff,greaseBuff,claymanBuff

EPW=pd.read_csv("data/EquipParamWeapon.csv").dropna(subset="Name").replace("Great epee","Great Épée",regex=True)
RPW=pd.read_csv("data/ReinforceParamWeapon.csv")
CCG=pd.read_csv("data/CalcCorrectGraph.csv")
AECP=pd.read_csv("data/AttackElementCorrectParam.csv")
RD=pd.read_csv("data/Raw_Data.csv").replace("Great Epee","Great Épée")
PAA=pd.read_csv("data/Physical AtkAttribute.csv").dropna(subset="Weapon").replace("Miséricorde","Misericorde").replace("Varré's Bouquet","Varre's Bouquet").iloc[:,:60].drop(
    columns=["1h Charged R2 1","1h Charged R2 2","2h Charged R2 1","2h Charged R2 2","1h Guard Counter","2h Guard Counter"])

def weaponsOfClass(wClass:str)->list[str]:
    # returns a list of all weappons of the specified class
    classes={v:k for k,v in idWeaponClass.items()}
    tmp=EPW[EPW["wepType"]==classes[wClass.replace("2H ","")]]
    return [f"2H {w}" if "2H" in wClass else w for w in tmp[tmp["reinforceTypeId"].isin([0,2200])]["Name"]]

# Calculations

def ARcalculator(weapon:str,infusion:str,build:list[int],reinforcementLvl:int=25)->np.ndarray:
    """
    Calculates weapon AR
    Parameters:
        weapon: string
            Weapon name.
        infusion: string
            Infusion name.
        build: list of length 5
            STR, DEX, INT, FTH, ARC.
        reinforcementLvl: int
            Weapon reinforcement level (normal, not somber).
    Output:
        numpy array of length 8
    """
    def CalcCorrectFormula(stat,ccgData):
        # used for stat scaling calculations
        for i in range(5):
            if ccgData.iloc[0,2+i]>stat:
                break
        statMin=ccgData.iloc[0,2+i-1]
        statMax=ccgData.iloc[0,2+i]
        ratio=(stat-statMin)/(statMax-statMin)
        expMin=ccgData.iloc[0,12+i-1]
        growth=ratio**expMin if expMin>0 else 1-(1-ratio)**abs(expMin)
        growthMin=ccgData.iloc[0,7+i-1]
        growthMax=ccgData.iloc[0,7+i]
        return (growthMin+(growthMax-growthMin)*growth)/100
    weaponName=weapon.replace("2H ","")
    if RD[RD["Name"]==weaponName]["Max Upgrade"].values[0]==10: reinforcementLvl=(reinforcementLvl+1)//2.5
    ID=EPW[EPW["Name"]==weaponName]["ID"].values[0]+infusionOffset[infusion]
    rtID=EPW[EPW["ID"]==ID]["reinforceTypeId"].values[0]
    ccgID=EPW[EPW["ID"]==ID][["correctType_Physics","correctType_Magic","correctType_Fire","correctType_Thunder","correctType_Dark"]].values[0]
    aecID=EPW[EPW["ID"]==ID]["attackElementCorrectId"].values[0]
    baseDmg=EPW[EPW["ID"]==ID][["attackBasePhysics","attackBaseMagic","attackBaseFire","attackBaseThunder","attackBaseDark"]].to_numpy()[0]
    baseScaling=EPW[EPW["ID"]==ID][["correctStrength","correctAgility","correctMagic","correctFaith","correctLuck"]].to_numpy()[0]/100
    baseDmgreinforcement=RPW[RPW["ID"]==rtID+reinforcementLvl][["Physical Attack","Magic Attack","Fire Attack","Lightning Attack","Holy Attack"]].to_numpy()[0]
    baseScalingreinforcement=RPW[RPW["ID"]==rtID+reinforcementLvl][["Str Scaling","Dex Scaling","Int Scaling","Fai Scaling","Arc Scaling"]].to_numpy()[0]
    dmg=baseDmg*baseDmgreinforcement # element
    scaling=baseScaling*baseScalingreinforcement # stat
    tmp=baseDmg*baseDmgreinforcement
    for i in range(5): #element
        if dmg[i]:
            for j in range(5): #stat
                if AECP[AECP["Row ID"]==aecID].iloc[0,1+5*i+j]:
                    stat=int(build[j]*1.5) if (j==0 and "2H" in weapon) else build[j]
                    tmp[i]+=dmg[i]*scaling[j]*CalcCorrectFormula(stat,CCG[CCG["ID"]==ccgID[i]])
    # convert 5-array into 8-array
    physType={}
    for attack in PAA[PAA["Weapon"]==weaponName].iloc[:,2:].values[0]:
        if pd.isna(attack) or "(" in attack: continue
        attack=attack.split(" + ")[0]
        if attack not in physType: physType[attack]=1
        else: physType[attack]+=1
    physType=max(physType,key=physType.get) #we get Standard, Strike, Slash or Pierce
    physType={"Standard":0,"Strike":1,"Slash":2,"Pierce":3}[physType]
    res=np.concatenate([[0,0,0,0],tmp[1:]])
    res[physType]=tmp[0]
    return(res)

def ARtoDMG(AR:list[int],defenses:list[int],negations:list[int])->np.ndarray:
    """
    Converts an AR array to a real damage array
    Parameters:
        AR: list of length 8
            AR for each damage type.
        defenses: list of length 8
            Defenses for each damage type.
        negations: list of length 8
            Negations for each damage type.
    Output:
        numpy array of length 8
    """
    res=[]
    for ar,d,n in zip(AR,defenses,negations):
        n/=100
        if d>ar*8:
            res.append((1-n)*0.1*ar) 
        elif d>ar:
            res.append((1-n)*(19.2/49*(ar/d-0.125)**2+0.1)*ar)
        elif d>ar*0.4:
            res.append((1-n)*(-0.4/3*(ar/d-2.5)**2+0.7)*ar)
        elif d>ar/8:
            res.append((1-n)*(-0.8/121*(ar/d-8)**2+0.9)*ar)
        else:
            res.append((1-n)*0.9*ar)
    return np.array(res)

def DMGtable(weapons:list[str],builds:dict[str,list[int]],infusions:dict[str,list[int]],defenses:list[int],negations:list[int],reinforcementLvl:int=25,weaponBuffs:bool=True,counterHits:bool=True,hardtear:bool=True)->pd.DataFrame:
    """
    Computes damage for each weapon/infusion/build combination.
    Parameters:
        weapons: list of string
            List of weapon names.
        builds: dict {string:list of int of length 5}
            Dict of builds with the keys being build name and values being STR DEX INT FTH ARC.
        infusions: dict {string:list of strings}
            Dict to specify what infusions we want for each build. Keys are build names and values are list of infusions.
        defenses: list of length 8
            Defenses for each damage type.
        negations: list of length 8
            Negations for each damage type.
        weaponBuffs: boolean
            Display weapon buffs like greases or Flaming Strike/Sacred Blade.
        counterHits: boolean
            Display counter hit damage and spear tali counter hit damage
    """
    res=[]
    if hardtear: negations=[n*1.1 for n in negations]
    for weapon in weapons:
        weaponName=weapon.replace("2H ","")
        if EPW[EPW["Name"]==weaponName].empty:
            print(f"Weapon does not exist: {weapon}")
            continue
        infusable=RD[RD["Name"]==weaponName]["Infusable"].values[0]=="Yes"
        buffable=EPW[EPW["Name"]==weaponName]["isEnhance"].values[0]==1
        weaponClass=idWeaponClass[EPW[EPW["Name"]==weaponName]["wepType"].values[0]]
        columns=[]
        normal,prc,spr=[],[],[]
        for build in builds:
            weaponInfusions=infusions[build] if infusable else ["Standard"]
            for infusion in weaponInfusions:
                dmg=ARtoDMG(ARcalculator(weapon,infusion,builds[build],reinforcementLvl),defenses,negations)
                normal.append(dmg.sum())
                if counterHits and dmg[3]:
                    prc.append((dmg*np.array([1,1,1,1.15,1,1,1,1])).sum())
                    spr.append((dmg*np.array([1,1,1,1.15*1.15,1,1,1,1])).sum())
                columns.append((f"{build} • {' '.join(map(str,builds[build]))}",infusion))
                # compute buffs (grease, flaming strike etc)
                # buffable     split     infusable: clayman
                # buffable     split not infusable: treespear, great club, troll's hammer
                # buffable not split not infusable: bhf, bouquet, ripple*2
                if weaponBuffs and buffable:
                    if not (infusion in forbiddenAshBuff and weaponClass in forbiddenAshBuff[infusion]):
                        if weaponName in rareBuff: buff=rareBuff[weaponName]
                        elif infusion in ashBuff: buff=ashBuff[infusion]
                        elif infusion in greaseBuff: buff=greaseBuff[infusion] if weaponName!="Clayman's Harpoon" else claymanBuff[infusion]
                        else: continue
                        dmg=ARtoDMG(ARcalculator(weapon,infusion,builds[build],reinforcementLvl)+buff[1],defenses,negations)
                        normal.append(dmg.sum())
                        if counterHits and dmg[3]:
                            prc.append((dmg*np.array([1,1,1,1.15,1,1,1,1])).sum())
                            spr.append((dmg*np.array([1,1,1,1.15*1.15,1,1,1,1])).sum())
                        columns.append((f"{build} • {' '.join(map(str,builds[build]))}",buff[0]))
        if columns:
            res.append(pd.DataFrame([normal,prc,spr],index=pd.MultiIndex.from_tuples([(weapon,"No Prc"),(weapon,"Prc+15%"),(weapon,"Prc+32%")]),columns=pd.MultiIndex.from_tuples(columns)))
    res=pd.concat(res).dropna(how="all")
    # reorder columns to respect infusion order
    res=res.sort_index(axis=1,level=1,sort_remaining=False,key=lambda x:x.map({a:i for i,a in enumerate(infusionOrder)}))
    res=res.sort_index(axis=1,level=0,sort_remaining=False,key=lambda x:x.map({a:i for i,a in enumerate(res.columns.get_level_values(0).unique())}))
    # add weapon class to index
    res.index=pd.MultiIndex.from_tuples([(f"{'2H ' if '2H' in w else ''}{idWeaponClass[EPW[EPW['Name']==w.replace('2H ','')]['wepType'].values[0]]}",w,d) for w,d in res.index])
    return res

def fancyTable(DMGtable:pd.DataFrame,classComparison:bool=True,displayPercentage:bool=True,showStats:bool=True,multicolor:bool=True,showWeaponClass:bool=True,wideDisplay:bool=False,saveOutput:bool=False)->None:
    """
    Displays a fancy damage table.
    Parameters:
        DMGtable: MultiIndexed pandas DataFrame
            Columns are build>infusion. Rows are weapon name>pierce bonus
        classComparison: boolean
            Compare the weapon with the best of its class.
        displayPercentage: boolean
            Display percentage value in cell.
        showStats: boolean
            Display build stat spread in column header.
        multicolor: boolean
            Display one color per build.
        showWeaponClass: boolean
            Display weapon class.
        wideDisplay: boolean
            Display a scrollable table instead of wider cells.
        saveOutput: boolean
            Save output as png.
    """
    tmp=DMGtable.apply(np.floor).astype("Int64")
    # sort by damage
    classes=tmp.index.get_level_values(0).unique() # we want to keep weapon class order most likely
    orderDesc=tmp.loc[pd.IndexSlice[:,:,"No Prc"],:].max(axis=1).sort_values(ascending=False).index.get_level_values(1)
    tmp=tmp.sort_index(level=1,key=lambda x:x.map({ii:i for i,ii in enumerate(orderDesc)}))
    tmp=tmp.sort_index(level=0,sort_remaining=False,key=lambda x:x.map({ii:i for i,ii in enumerate(classes)})) # restore class order
    # percentages
    if not classComparison:
        DMGratio=tmp.apply(lambda x:x/x.max()*100-100,axis=1).astype(float)
    else:
        DMGratio=tmp.apply(lambda x:x/tmp.loc[pd.IndexSlice[x.name[0],:,x.name[2]],:].max().max()*100-100,axis=1).astype(float)
    res=tmp.copy()
    for c in tmp.columns:
        if displayPercentage:
            res[c]=res[c].map(lambda x:str(x).replace("<NA>","-"))+DMGratio[c].map(lambda x:"" if pd.isna(x) else "(👑)" if x==0 else "("+f"{x:.2f}"[:5]+"%)")
        else:
            res[c]=res[c].map(lambda x:str(x).replace("<NA>","-"))
    # display max of each row in bold
    res=res.style.format(precision=1).apply(lambda x:tmp.apply(lambda x:x.apply(lambda xx:"font-weight: bold" if not pd.isna(xx) and xx==x.max() else ""),axis=1),axis=None) # miracle
    # background color
    vmin=-15
    for i in tmp.index:
        if not multicolor:
            res.background_gradient(cmap="Greens",axis=None,gmap=DMGratio.fillna(vmin),vmin=vmin,vmax=0)
        else:
            cmaps=[["white","red"],["white","gold"],["white","blue"],["white","orange"],["white","violet"]]
            for j,jj in enumerate(tmp.columns.get_level_values(0).unique()):
                res.background_gradient(cmap=LinearSegmentedColormap.from_list("",cmaps[j%5]),axis=None,gmap=DMGratio.fillna(vmin),subset=(i,tmp[[jj]].columns),vmin=vmin,vmax=0)
    # weapon class display and hide pierce bonus if useless
    hide=[]
    if not showWeaponClass:
        hide.append(0)
    if tmp.index.get_level_values(2).drop_duplicates().size==1:
        hide.append(2)
    res=res.hide(level=hide)
    # center values
    res.set_table_styles([{'selector': 'td, th.col_heading', 'props': 'text-align: center;'}],overwrite=False)
    # borders
    for i in [j for i,j in zip(tmp.columns[:-1],tmp.columns[1:]) if i[0]!=j[0]]:
        res.set_table_styles({i: [{'selector': '', 'props': 'border-left: 1px solid grey;'}]},overwrite=False)
    if res.index.nlevels>1:
        for i in [j for i,j in zip(tmp.index[:-1],tmp.index[1:]) if i[0]!=j[0]]:
            res.set_table_styles({i: [{'selector': '', 'props': 'border-top: 1px solid grey;'}]},overwrite=False, axis=1)
    # stats
    if not showStats:
        res.format_index(lambda x:x.split("•")[0].rstrip(),axis=1)
    return(res)
