/* Project-authored DSH native conversation extension; no iframe or second chat backend. */
window.__ModuleLoader__.load({id:'nexusmore-harness',factory:require=>{
  const React=require('react'), h=React.createElement;
  const KIND='nexusmore-question',TYPE='nexusmore-harness/question';
  const address=id=>'dsh-resource://nexusmore-question/'+id;
  const inject=['slots','sidebarRight','sidebarRightTabs','sessions','remote','remote.commands'];
  async function apply(ctx){
    const registrations=[];
    const register=async setup=>{const effect=ctx.effect(setup);registrations.push(effect);await effect;};
    try{
    const command=async(session,line)=>{
      const response=await ctx.remote.commands.execute(session,line,[]);
      if(!response.ok||response.value?.result?.kind==='error')throw new Error(response.value?.result?.text??'操作未完成，请查看当前会话。');
      return response.value?.result;
    };
    // DSH's Markdown anchor defaults to a web link for custom schemes.
    // Route file links to its existing native file tab instead of a browser.
    if(typeof document!=='undefined')await register(()=>{
      const openFile=event=>{
        const anchor=event.target?.closest?.('a[href]'),href=anchor?.getAttribute('href');
        const match=/^dsh-resource:\/\/file\/session\/(session-[A-Za-z0-9-]+)\//.exec(href??'');
        if(!match||event.button>0)return;
        event.preventDefault();event.stopPropagation();
        try{ctx.sidebarRight.openResourceIn(match[1],href);}
        catch{console.error('NexusMORE native file preview could not open; retain the draft and check the DSH file plugin.');}
      };
      document.addEventListener('click',openFile,true);
      return ()=>document.removeEventListener('click',openFile,true);
    });
    function Controls({sessionId,compact=false}){
      const [busy,setBusy]=React.useState(false),[notice,setNotice]=React.useState('');
      React.useEffect(()=>{
        const controller=new AbortController();
        if(sessionId)fetch('/api/nexusmore/conversation?session='+encodeURIComponent(sessionId),{signal:controller.signal,cache:'no-store'})
          .then(r=>{if(!r.ok)throw Error('Navigation unavailable');return r.json();})
          .then(value=>{if(!controller.signal.aborted)for(const child of value.children??[])
            ctx.sidebarRight.openResourceIn(sessionId,address(child.session_id),{kind:KIND,params:{session_id:child.session_id}});})
          .catch(()=>{if(!controller.signal.aborted)setNotice('下一题导航未恢复，请检查连接后重开会话。');});
        return ()=>controller.abort();
      },[sessionId]);
      async function act(mode){
        if(busy)return;setBusy(true);setNotice('正在处理…');
        try{
          const result=await command(sessionId,mode==='start'?'/nexusmore-start-question':mode==='next'?'/nexusmore-next-question':mode==='review'?'/nexusmore-current-review':'/nexusmore-current-status');
          if(mode==='next'||mode==='start'){
            const created=JSON.parse(result.text);
            ctx.sidebarRight.openResourceIn(sessionId,address(created.session_id),{kind:KIND,params:{session_id:created.session_id}});
            setNotice(mode==='start'?'小题会话已打开，直接输入题目即可。':'下一题已在旁边打开。');
          }else setNotice(mode==='status'?'已查询原回执，请查看会话记录。':'待审文件已发到对话中；查看后可回复“通过”或提出修改意见。');
        }catch(error){setNotice(error.message);}
        finally{setBusy(false);}
      }
      return h('div',{'data-nexusmore-controls':sessionId,style:{display:'flex',flexWrap:'wrap',gap:8,alignItems:'center',padding:'4px 8px',minWidth:0,maxWidth:compact?220:'100%'}},
        h('button',{type:'button',disabled:busy,onClick:()=>act('start'),title:'打开用户专属工作区，直接输入题目，无需命令',style:{padding:'6px 10px',minHeight:44,borderRadius:6,border:'1px solid currentColor',background:'transparent',color:'inherit',font:'inherit',cursor:'pointer'}},'开始小题'),
        h('button',{type:'button',style:{padding:'6px 10px',borderRadius:6,border:'1px solid currentColor',background:'transparent',color:'inherit',font:'inherit',cursor:'pointer'},disabled:busy,onClick:()=>act('review'),title:'审阅当前小题，无需输入命令或对象编号'},'审阅当前题'),
        h('button',{type:'button',style:{padding:'6px 10px',borderRadius:6,border:'1px solid currentColor',background:'transparent',color:'inherit',font:'inherit',cursor:'pointer'},disabled:busy,onClick:()=>act('status')},'查询原回执'),
        h('button',{type:'button',style:{padding:'6px 10px',borderRadius:6,border:'1px solid currentColor',background:'transparent',color:'inherit',font:'inherit',cursor:'pointer'},disabled:busy,onClick:()=>act('next')},'继续下一题'),
        h('span',{role:'status','aria-live':'polite',style:{fontSize:12,maxWidth:280}},notice));
    }
    function Embedded({renderFactorySlot}){
      return renderFactorySlot('conversation.content',{variant:'embedded',phase:'active',hero:false});
    }
    function Question({useTabInfo,SessionProvider,renderSlot}){
      const {tab}=useTabInfo(),id=tab.navigation.params?.session_id??tab.contentId?.split('/').at(-1);
      const [reference,setReference]=React.useState(),[error,setError]=React.useState('');
      React.useEffect(()=>{
        if(typeof id!=='string'||!/^session-[A-Za-z0-9-]+$/.test(id)){setError('下一题会话不存在。');return;}
        const retained=ctx.sessions.retain(id,{source:'nexusmore-question'});let live=true;
        retained.ready.then(()=>{if(live)setReference(retained);},()=>{if(live)setError('下一题会话未能恢复，请保留原会话并重试。');});
        return ()=>{live=false;retained.release();};
      },[id]);
      if(error)return h('p',{role:'alert'},error);
      if(!reference)return h('p',{role:'status'},'正在恢复下一题…');
      return h('section',{'data-nexusmore-next-session':id,style:{height:'100%',minHeight:0,display:'flex',flexDirection:'column'}},
        h('div',{style:{padding:10,borderBottom:'1px solid var(--dsw-alias-border-l2-darkmode-thin)'}},'小题 · 独立会话'),
        h('div',{style:{flex:1,minHeight:0,display:'flex',flexDirection:'column'}},
          h(SessionProvider,{session:reference},renderSlot('nexusmore.question.content',{}))));
    }
    await register(()=>ctx.sidebarRightTabs.register({id:TYPE,kind:KIND,priority:'extension',multiple:true,canOpen:value=>/^dsh-resource:\/\/nexusmore-question\/session-[A-Za-z0-9-]+$/.test(value),title:()=> '枢模 · 小题'}));
    await register(()=>ctx.slots.inject('conversation.session.header.utilities',()=>ctx.slots.register({name:'conversation.session.header.utilities',id:'nexusmore-controls'},Controls)));
    await register(()=>ctx.slots.inject('conversation.hero.options',()=>ctx.slots.register({name:'conversation.hero.options',id:'nexusmore-controls'},function HeroControls(props){return h(Controls,{...props,compact:true});})));
    await register(()=>ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({
      name:'sidebar.right.pane.tab',key:TYPE,children:{'nexusmore.question.content':{kind:'single',scope:'session'}}
    },Question)));
    await register(()=>ctx.slots.inject('nexusmore.question.content',()=>ctx.slots.register({
      name:'nexusmore.question.content',children:{'nexusmore.question.controls':{kind:'single',scope:'session'}}
    },function Body(props){return h(React.Fragment,null,props.renderSlot('nexusmore.question.controls',{}),h(Embedded,props));})));
    await register(()=>ctx.slots.inject('nexusmore.question.controls',()=>ctx.slots.register({name:'nexusmore.question.controls'},Controls)));
    }catch{
      for(const dispose of registrations.reverse())try{await dispose();}catch{}
      // Keep the host usable. G3 native commands remain available for diagnosis/recovery.
      console.error('NexusMORE optional conversation UI did not activate; use native review commands and check plugin compatibility.');
    }
  }
  return {apply,inject};
}});
