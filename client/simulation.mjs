 // FMC1 portable ESM client: runs in browsers and Node.js without dependencies.
 const MAGIC="FMC1", R=6371008.8, RAD=Math.PI/180;
 function check(x,msg){if(!x)throw Error(msg);}
 export function readPackage(input){
   const b=input instanceof ArrayBuffer?new Uint8Array(input):new Uint8Array(input.buffer,input.byteOffset,input.byteLength);
   const v=new DataView(b.buffer,b.byteOffset,b.byteLength);
   check(b.byteLength>=20,"Short FMC1 package");
   check(String.fromCharCode(...b.subarray(0,4))===MAGIC,"Invalid FMC1 signature");
   const metaLength=v.getUint32(4,true),n=v.getUint32(8,true),m=v.getUint32(12,true),k=v.getUint32(16,true);
   check(n>0&&k>0&&k<=32&&20+metaLength<=b.byteLength,"Invalid FMC1 header");
   const meta=JSON.parse(new TextDecoder().decode(b.subarray(20,20+metaLength)));
   check(meta.format_version===1&&meta.categories?.length===k,"Unsupported FMC1 metadata");
   let pos=Math.ceil((20+metaLength)/8)*8;
   check(pos+8*(3*n+n*k)+4*(n+1)+12*m===b.byteLength,"Invalid FMC1 length");
   function doubles(count){const a=new Float64Array(count);for(let i=0;i<count;i++,pos+=8)a[i]=v.getFloat64(pos,true);return a;}
   function ints(count){const a=new Uint32Array(count);for(let i=0;i<count;i++,pos+=4)a[i]=v.getUint32(pos,true);return a;}
   const coordinates=doubles(2*n),population=doubles(n),baseline=doubles(n*k);
   const offsets=ints(n+1),targets=ints(m),travelTime=doubles(m);
   check(offsets[0]===0&&offsets[n]===m,"Invalid CSR endpoints");
   for(let i=0;i<n;i++){
     check(offsets[i]<=offsets[i+1]&&Number.isFinite(population[i])&&population[i]>=0,"Invalid node data");
     for(let j=0;j<k;j++){const d=baseline[i*k+j];check(d===Infinity||(Number.isFinite(d)&&d>=0),"Invalid baseline time");}
   }
   for(let i=0;i<m;i++)check(targets[i]<n&&Number.isFinite(travelTime[i])&&travelTime[i]>=0,"Invalid edge");
   return {meta,nodeCount:n,edgeCount:m,categoryCount:k,coordinates,population,baseline,offsets,targets,travelTime};
 }
 function nearest(p,lon,lat,limit){
   let distance=Infinity,index=-1;
   for(let i=0;i<p.nodeCount;i++){
     const x=(lon-p.coordinates[2*i])*RAD*Math.cos((lat+p.coordinates[2*i+1])*RAD/2);
     const y=(lat-p.coordinates[2*i+1])*RAD;
     const d=R*Math.hypot(x,y);
     if(d<distance){distance=d;index=i;}
   }
   check(distance<=limit,"Service too far from walking network: "+distance.toFixed(1)+" m");
   return {index,metres:distance};
 }
 class Heap{
   constructor(){this.q=[];}
   push(node,dist){
     let i=this.q.length;this.q.push([node,dist]);
     while(i){const j=(i-1)>>>1;if(this.q[j][1]<=dist)break;this.q[i]=this.q[j];i=j;}
     this.q[i]=[node,dist];
   }
   pop(){
     const a=this.q,head=a[0],end=a.pop();
     if(a.length){let i=0;while(2*i+1<a.length){
       let j=2*i+1;if(j+1<a.length&&a[j+1][1]<a[j][1])j++;
       if(a[j][1]>=end[1])break;a[i]=a[j];i=j;
     }a[i]=end;}return head;
   }
   get size(){return this.q.length;}
 }
 function dijkstra(p,sources){
   const dist=new Float64Array(p.nodeCount);dist.fill(Infinity);
   const heap=new Heap();
   for(const id of new Set(sources)){dist[id]=0;heap.push(id,0);}
   while(heap.size){
     const [id,d]=heap.pop();if(d>dist[id])continue;
     for(let i=p.offsets[id];i<p.offsets[id+1];i++){
       const to=p.targets[i],next=d+p.travelTime[i];
       if(next<dist[to]){dist[to]=next;heap.push(to,next);}
     }
   }
   return dist;
 }
 function median(pairs){
   if(!pairs.length)return null;
   pairs.sort((a,b)=>a[0]-b[0]);
   let cum=0,half=pairs.reduce((s,x)=>s+x[1],0)/2;
   for(const [t,w] of pairs){cum+=w;if(cum>=half)return t/60;}
   return pairs.at(-1)[0]/60;
 }
 function metrics(p,updates,weighted){
   const n=p.nodeCount,k=p.categoryCount,threshold=p.meta.threshold_minutes*60;
   const total=weighted?p.population.reduce((sum,x)=>sum+x,0):n;
   check(total>0,"No population data");
   const all=new Uint8Array(n).fill(1),unreachable=new Uint8Array(n),categories={};
   for(let c=0;c<k;c++){
     const improved=updates.get(c);let within=0,reachable=0,weightedSeconds=0;
     const observations=[];
     for(let i=0;i<n;i++){
       const w=weighted?p.population[i]:1;
       const old=p.baseline[i*k+c],t=improved?Math.min(old,improved[i]):old;
       if(t!==Infinity){reachable+=w;weightedSeconds+=w*t;if(w>0)observations.push([t,w]);}
       else unreachable[i]=1;
       if(t<=threshold)within+=w;else all[i]=0;
     }
     categories[p.meta.categories[c]]={
       coverage_percentage:100*within/total,
       unreachable_percentage:100*(total-reachable)/total,
       mean_travel_time_minutes:reachable?weightedSeconds/(reachable*60):null,
       median_travel_time_minutes:median(observations)
     };
   }
   let covered=0,unreachableWeight=0;
   for(let i=0;i<n;i++){
     const w=weighted?p.population[i]:1;
     if(all[i])covered+=w;if(unreachable[i])unreachableWeight+=w;
   }
   return {categories,overall_coverage_percentage:100*covered/total,overall_unreachable_percentage:100*unreachableWeight/total};
 }
 function delta(a,b){
   const cats={};for(const code of Object.keys(a.categories))cats[code]=b.categories[code].coverage_percentage-a.categories[code].coverage_percentage;
   return {unit:"percentage_points",category_coverage:cats,overall_coverage:b.overall_coverage_percentage-a.overall_coverage_percentage};
 }
 export function simulate(pkg,services,options={}){
   const max=options.maxSnapDistanceM??250;
   check(Number.isFinite(max)&&max>0,"Invalid snapping distance");
   check(Array.isArray(services)&&services.length>=1&&services.length<=200,"Expected 1 to 200 hypothetical services");
   const byCategory=new Map(),placed=[];
   for(const item of services){
     check(item&&typeof item==="object","Invalid service");
     const c=pkg.meta.categories.indexOf(item.category);
     check(c>=0,"Category not analyzed: "+item.category);
     check(Number.isFinite(item.longitude)&&Number.isFinite(item.latitude)&&
       Math.abs(item.longitude)<=180&&Math.abs(item.latitude)<=90,"Invalid geographic coordinates");
     const {index,metres}=nearest(pkg,item.longitude,item.latitude,max);
     if(!byCategory.has(c))byCategory.set(c,[]);
     byCategory.get(c).push(index);
     placed.push({name:typeof item.name==="string"?item.name:null,category:item.category,
       longitude:item.longitude,latitude:item.latitude,graph_node_index:index,snap_distance_m:metres});
   }
   const changed=new Map();
   for(const [category,sources] of byCategory)changed.set(category,dijkstra(pkg,sources));
   const baseline={population:metrics(pkg,new Map(),true),nodes:metrics(pkg,new Map(),false)};
   const simulated={population:metrics(pkg,changed,true),nodes:metrics(pkg,changed,false)};
   return {execution_id:pkg.meta.execution_id,added_services:placed,baseline,simulated,
     delta:{population:delta(baseline.population,simulated.population),nodes:delta(baseline.nodes,simulated.nodes)}};
 }
