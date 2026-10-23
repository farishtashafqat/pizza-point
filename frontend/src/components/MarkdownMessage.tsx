import { Fragment } from 'react';

const namedEntities:Record<string,string>={amp:'&',apos:"'",gt:'>',lt:'<',nbsp:' ',quot:'"'};
function decodeEntities(value:string){return value.replace(/&(#x[0-9a-f]+|#\d+|amp|apos|gt|lt|nbsp|quot);/gi,(_,entity:string)=>{const lower=entity.toLowerCase();if(lower[0]!=='#')return namedEntities[lower]||_;const point=lower.startsWith('#x')?Number.parseInt(lower.slice(2),16):Number.parseInt(lower.slice(1),10);return Number.isSafeInteger(point)&&point>=0&&point<=0x10ffff?String.fromCodePoint(point):_})}
const normalized=(value:string)=>decodeEntities(value).replace(/\\n/g,'\n').replace(/\r\n?/g,'\n');
const cells=(line:string)=>line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());
const separator=(line:string)=>/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line);

function inline(text:string){
 const pieces=text.split(/(\*\*[^*]+\*\*|__[^_]+__)/g);
 return pieces.map((piece,index)=>piece.startsWith('**')&&piece.endsWith('**')?<strong key={index}>{piece.slice(2,-2)}</strong>:piece.startsWith('__')&&piece.endsWith('__')?<strong key={index}>{piece.slice(2,-2)}</strong>:<Fragment key={index}>{piece}</Fragment>);
}

/** Safe Markdown subset: text stays React-escaped and HTML is never interpreted. */
export default function MarkdownMessage({content}:{content:string}){
 const lines=normalized(content).split('\n'),blocks:React.ReactNode[]=[];
 for(let index=0;index<lines.length;){
  const line=lines[index];
  if(!line.trim()){index++;continue}
  if(line.trim()==='---'){blocks.push(<hr key={index}/>);index++;continue}
  if(line.includes('|')&&index+1<lines.length&&separator(lines[index+1])){const header=cells(line);index+=2;const rows:string[][]=[];while(index<lines.length&&lines[index].includes('|')&&lines[index].trim()){rows.push(cells(lines[index++]));}blocks.push(<div className="markdown-table-wrap" key={index}><table><thead><tr>{header.map((cell,i)=><th key={i}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row,rowIndex)=><tr key={rowIndex}>{header.map((_,cellIndex)=><td key={cellIndex}>{inline(row[cellIndex]||'')}</td>)}</tr>)}</tbody></table></div>);continue}
  const list=/^\s*[-*+]\s+(.+)$/.exec(line),ordered=/^\s*\d+[.)]\s+(.+)$/.exec(line);
  if(list||ordered){const type=ordered?'ol':'ul',items:string[]=[];while(index<lines.length){const match=(ordered?/^\s*\d+[.)]\s+(.+)$/:/^\s*[-*+]\s+(.+)$/).exec(lines[index]);if(!match)break;items.push(match[1]);index++;}const Tag=type;blocks.push(<Tag key={index}>{items.map((item,i)=><li key={i}>{inline(item)}</li>)}</Tag>);continue}
  blocks.push(<p key={index}>{inline(line)}</p>);index++;
 }
 return <div className="markdown-message">{blocks}</div>;
}
