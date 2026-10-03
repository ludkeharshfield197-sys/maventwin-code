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
fig,axes=plt.subplots(1,3,figsize=(10.3,4.25));fig.subplots_adjust(left=.03,right=.99,top=.88,bottom=.16,wspace=.16)
items=[('Effective model',50,[20,18,12],['Source-POM linked','Runtime/default','Unresolved'],['#0072B2','#009E73','#E69F00']),('Dependency graph',53,[2,51],['Different','Identical'],['#D55E00','#B7C9D6']),('Root validation',47,[36,3,1,7],['Pass/pass','Pass/fail','Fail/pass','Fail/fail'],['#009E73','#D55E00','#56B4E9','#9A7AB5'])]
for ax,(title,total,counts,labels,colors) in zip(axes,items):
    ax.set_title(f'{title}\n(n = {total})',fontsize=13,fontweight='bold',pad=12)
    left=0
    for count,label,color in zip(counts,labels,colors):
        ax.barh(.86,count,left=left,height=.19,color=color,edgecolor='white',linewidth=1)
        if count>=6:ax.text(left+count/2,.86,str(count),ha='center',va='center',color='white' if color!='#B7C9D6' else '#152C3C',fontsize=13,fontweight='bold')
        left+=count
    ax.set_xlim(0,total);ax.set_ylim(0,1);ax.axis('off')
    ax.legend([Patch(facecolor=c) for c in colors],[f'{l}: {n}' for l,n in zip(labels,counts)],loc='upper left',bbox_to_anchor=(-.01,.73),frameon=False,fontsize=10.5,handlelength=1.3,labelspacing=.7)
axes[0].text(0,.10,'Shared-default ablation:\n34/50 retain differences',fontsize=10.5,color='#334D5C',va='bottom')
axes[1].text(0,.10,'Both changed graphs reproduce\nwith frozen offline inputs',fontsize=10.5,color='#334D5C',va='bottom')
axes[2].text(0,.10,'Initial pass/fail records:\n2 reproduce; 1 passes on full checkout',fontsize=10,color='#334D5C',va='bottom')
for ext in ['pdf','png']:fig.savefig(FIG/f'Figure2_layer_counts.{ext}',dpi=240,bbox_inches='tight',facecolor='white')
print('Figure 2 updated')
