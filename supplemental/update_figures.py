from pathlib import Path
import shutil,os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
HERE=Path(__file__).resolve().parent;FIG=Path(os.environ.get('MAVENTWIN_FIGURE_OUTPUT',HERE/'figures'));FIG.mkdir(parents=True,exist_ok=True)
for ext in ['pdf','png']:
    src=FIG/f'Figure2_layer_counts.{ext}';dst=HERE/'before'/src.name
    if src.exists() and not dst.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'pdf.fonttype':42,'ps.fonttype':42})
fig,grid=plt.subplots(2,2,figsize=(10.3,6.3));axes=grid.flatten();fig.subplots_adjust(left=.08,right=.98,top=.91,bottom=.12,wspace=.25,hspace=.37)
items=[('Effective model',50,[20,18,12],['Source-POM linked','Runtime/default','Unresolved'],['#0072B2','#009E73','#E69F00']),('Dependency graph',53,[2,51],['Different','Identical'],['#D55E00','#B7C9D6']),('Root validation',47,[36,3,1,7],['Pass/pass','Pass/fail','Fail/pass','Other/mixed'],['#009E73','#D55E00','#56B4E9','#9A7AB5'])]
for ax,(title,total,counts,labels,colors) in zip(axes,items):
    ax.set_title(f'{title} (n = {total})',fontsize=15,fontweight='bold',pad=12)
    left=0
    for count,label,color in zip(counts,labels,colors):
        ax.barh(.86,count,left=left,height=.19,color=color,edgecolor='white',linewidth=1)
        if count>=6:ax.text(left+count/2,.86,str(count),ha='center',va='center',color='white' if color!='#B7C9D6' else '#152C3C',fontsize=13,fontweight='bold')
        left+=count
    ax.set_xlim(0,total);ax.set_ylim(0,1);ax.axis('off')
    ax.legend([Patch(facecolor=c) for c in colors],[f'{l}: {n}' for l,n in zip(labels,counts)],loc='upper left',bbox_to_anchor=(-.01,.73),frameon=False,fontsize=13,handlelength=1.3,labelspacing=.55)
axes[1].text(0,.10,'Both reproduce offline',fontsize=13,color='#334D5C',va='bottom')
axes[2].text(0,-.06,'Of three initial pass/fail records:\n2 reproduce; 1 passes on full checkout',fontsize=12,color='#334D5C',va='bottom')
ax=axes[3];labels=['All selected fields','No common site defaults','No runtime/default rows','No configuration fields','Source-POM linked'];counts=[50,34,32,31,20]
ax.set_title('Model ablations (n = 50)',fontsize=15,fontweight='bold',pad=12)
for i,(label,count) in enumerate(zip(labels,counts)):
    ax.barh(4-i,count,color='#0072B2' if i==0 else '#009E73',height=.58)
    ax.text(1,4-i,label,va='center',fontsize=11,color='white')
    ax.text(count+1,4-i,str(count),va='center',fontsize=13,fontweight='bold')
ax.set_yticks([]);ax.set_xlim(0,56);ax.set_xticks([0,25,50]);ax.tick_params(axis='both',length=0)
for spine in ax.spines.values():spine.set_visible(False)
ax.text(0,-1.25,'Separate row filters; positive repositories',fontsize=11,color='#334D5C')
for ext in ['pdf','png']:fig.savefig(FIG/f'Figure2_layer_counts.{ext}',dpi=240,bbox_inches='tight',facecolor='white')
print('Figure 2 updated')
