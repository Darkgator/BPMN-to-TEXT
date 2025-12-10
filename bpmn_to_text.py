"""
Gera narrativa hierárquica numerada a partir de um BPMN (tarefas, eventos,
gateways, atores/lanes, anotações, sistemas/documentos), cuidando de retornos
em convergência para evitar loops falsos e mantendo a numeração por caminhos.
Uso rápido: python bpmn_to_text.py "<arquivo>.bpmn" (ou .xml). Se não informar,
abre um BPMN padrão da pasta.
"""







import sys

import xml.etree.ElementTree as ET

from collections import defaultdict

from pathlib import Path

from typing import List, Dict, Tuple

import tempfile



NS = {

    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",

    "di": "http://www.omg.org/spec/BPMN/20100524/DI",

    "dc": "http://www.omg.org/spec/DD/20100524/DC",

}





def pick_process(defs):

    """Escolhe o processo principal: o primeiro que tiver startEvent."""

    processes = defs.findall("bpmn:process", NS)

    if not processes:

        raise ValueError("Nenhum processo encontrado no BPMN.")

    for proc in processes:

        if proc.findall("bpmn:startEvent", NS):

            return proc

    return processes[0]









def collect_elements(proc):
    """Extrai n?s (tarefas, gateways, eventos) e sequenceFlows, marcando links catch/throw."""
    nodes = {}
    link_by_name = defaultdict(lambda: {"catch": [], "throw": []})

    tag_map = {
        "task": "Atividade",
        "userTask": "Atividade (usu?rio)",
        "serviceTask": "Atividade (servi?o)",
        "sendTask": "Atividade (envio)",
        "receiveTask": "Atividade (recebimento)",
        "manualTask": "Atividade (manual)",
        "subProcess": "Subprocesso",
        "callActivity": "Subprocesso (call activity)",
        "exclusiveGateway": "Gateway exclusivo",
        "parallelGateway": "Gateway paralelo",
        "inclusiveGateway": "Gateway inclusivo",
        "eventBasedGateway": "Gateway baseado em evento",
        "startEvent": "Evento de in?cio",
        "endEvent": "Evento de fim",
        "intermediateThrowEvent": "Evento intermedi?rio",
        "intermediateCatchEvent": "Evento intermedi?rio",
        "boundaryEvent": "Evento intermedi?rio (fronteira)",
    }

    def event_flavor(elem):
        for child in elem:
            tag = child.tag.split('}')[-1]
            if tag.endswith('EventDefinition'):
                kind = tag.replace('EventDefinition', '')
                link_name = child.attrib.get('name', '').strip()
                return kind, link_name
        return '', ''

    for tag_key, human in tag_map.items():
        for elem in proc.findall(f"bpmn:{tag_key}", NS):
            detail, link_name = event_flavor(elem) if 'Event' in tag_key else ('', '')
            nodes[elem.attrib['id']] = {
                'type': human,
                'name': elem.attrib.get('name', ''),
                'kind': tag_key,
                'event_flavor': detail,
                'link_name': link_name,
                'catch_throw': '',
            }
            if tag_key == 'intermediateCatchEvent' and link_name:
                link_by_name[link_name]['catch'].append(elem.attrib['id'])
            if tag_key == 'intermediateThrowEvent' and link_name:
                link_by_name[link_name]['throw'].append(elem.attrib['id'])

    # Marca captura/disparo s? se houver ambos com o mesmo nome
    for nm, group in link_by_name.items():
        if group['catch'] and group['throw']:
            for cid in group['catch']:
                if cid in nodes:
                    nodes[cid]['catch_throw'] = 'captura'
            for tid in group['throw']:
                if tid in nodes:
                    nodes[tid]['catch_throw'] = 'disparo'

    flows = {}
    outgoing = defaultdict(list)
    incoming = defaultdict(list)

    for sf in proc.findall('bpmn:sequenceFlow', NS):
        flow_id = sf.attrib['id']
        flows[flow_id] = {
            'name': sf.attrib.get('name', '').strip(),
            'source': sf.attrib.get('sourceRef'),
            'target': sf.attrib.get('targetRef'),
        }
        outgoing[flows[flow_id]['source']].append(flow_id)
        incoming[flows[flow_id]['target']].append(flow_id)

    # Se um catch de link não tem incoming e há throw correspondente, insere o catch no caminho do seu target
    for nm, group in link_by_name.items():
        if not (group['catch'] and group['throw']):
            continue
        for cid in group['catch']:
            if incoming.get(cid):
                continue
            outs = outgoing.get(cid, [])
            # Se o catch tem outgoing (caso raro), apenas garante que incoming vazio não bloqueie
            if outs:
                continue
            # pega o primeiro flow do target original conectado ao throw correspondente
            for tid in group['throw']:
                if not outgoing.get(tid):
                    continue
                # usa o primeiro fluxo do throw
                first_out = outgoing[tid][0]
                tgt = flows[first_out]['target']
                # redireciona incoming do target para o catch
                for inc_id in list(incoming.get(tgt, [])):
                    flows[inc_id]['target'] = cid
                    incoming[cid].append(inc_id)
                    incoming[tgt].remove(inc_id)
                # cria fluxo catch -> target se não existir
                if not any(flows[f]['target'] == tgt for f in outgoing.get(cid, [])):
                    flow_id = f"_linkcatch_{cid}_{tgt}"
                    flows[flow_id] = {
                        'name': f"Link: {nm}" if nm else 'Link',
                        'source': cid,
                        'target': tgt,
                        'is_link': True,
                    }
                    outgoing[cid].append(flow_id)
                    incoming[tgt].append(flow_id)
                break

    # Se um throw de link não tem saída, cria fluxo sintético para o catch correspondente
    for nm, group in link_by_name.items():
        if not (group['catch'] and group['throw']):
            continue
        for tid in group['throw']:
            if outgoing.get(tid):
                continue
            for cid in group['catch']:
                flow_id = f"_link_{tid}_{cid}"
                flows[flow_id] = {
                    'name': f"Link: {nm}" if nm else 'Link',
                    'source': tid,
                    'target': cid,
                    'is_link': True,
                }
                outgoing[tid].append(flow_id)
                incoming[cid].append(flow_id)

    return nodes, flows, outgoing, incoming

def collect_lanes(proc):

    """Mapeia nós para lanes (por flowNodeRef) e retorna nomes das lanes."""

    node_lane = {}

    lane_name = {}

    for lane in proc.findall(".//bpmn:lane", NS):

        lid = lane.attrib.get("id")

        lname = lane.attrib.get("name", "") or "(sem ator)"

        if lid:

            lane_name[lid] = lname

        for ref in lane.findall("bpmn:flowNodeRef", NS):

            if ref.text:

                node_lane[ref.text.strip()] = lname

    return node_lane, lane_name





def collect_di_bounds(defs, node_ids, lane_ids):

    """Coleta Bounds dos BPMNShape para nós e lanes (para inferir ator via DI)."""

    node_bounds = {}

    lane_bounds = {}

    for shape in defs.findall(".//di:BPMNShape", NS):

        elem_id = shape.attrib.get("bpmnElement")

        bounds = shape.find("dc:Bounds", NS)

        if not elem_id or bounds is None:

            continue

        rect = (

            float(bounds.attrib.get("x", 0)),

            float(bounds.attrib.get("y", 0)),

            float(bounds.attrib.get("width", 0)),

            float(bounds.attrib.get("height", 0)),

        )

        if elem_id in node_ids:

            node_bounds[elem_id] = rect

        if elem_id in lane_ids:

            lane_bounds[elem_id] = rect

    return node_bounds, lane_bounds





def collect_artifacts(defs, node_ids: set) -> Dict[str, List[Tuple[str, str]]]:

    """Associa nós a documentos, sistemas e anotações, separando anotações órfãs."""

    annotations = {}

    for ta in defs.findall(".//bpmn:textAnnotation", NS):

        text_el = ta.find("bpmn:text", NS)

        if text_el is not None:

            text_val = (text_el.text or "").strip()

            if text_val:

                annotations[ta.attrib.get("id")] = ("Anotação", text_val)



    data_object_defs = {}

    for dobj in defs.findall(".//bpmn:dataObject", NS):

        name = (dobj.attrib.get("name") or "").strip()

        data_object_defs[dobj.attrib.get("id")] = name



    data_store_defs = {}

    for ds in defs.findall(".//bpmn:dataStore", NS):

        name = (ds.attrib.get("name") or "").strip()

        data_store_defs[ds.attrib.get("id")] = name



    data_objects = {}

    for dobj in defs.findall(".//bpmn:dataObjectReference", NS):

        ref = dobj.attrib.get("dataObjectRef")

        name = (dobj.attrib.get("name") or "").strip()

        if not name and ref in data_object_defs:

            name = data_object_defs.get(ref, "")

        name = name or dobj.attrib.get("id")

        data_objects[dobj.attrib.get("id")] = ("Documento", name)

    for dobj in defs.findall(".//bpmn:dataObject", NS):

        name = (dobj.attrib.get("name") or "").strip()

        name = name or dobj.attrib.get("id")

        data_objects[dobj.attrib.get("id")] = ("Documento", name)



    data_stores = {}

    for dstore in defs.findall(".//bpmn:dataStoreReference", NS):

        ref = dstore.attrib.get("dataStoreRef")

        name = (dstore.attrib.get("name") or "").strip()

        if not name and ref in data_store_defs:

            name = data_store_defs.get(ref, "")

        name = name or dstore.attrib.get("id")

        data_stores[dstore.attrib.get("id")] = ("Sistema", name)



    artifacts = {**annotations, **data_objects, **data_stores}

    by_node: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    attached_notes = set()



    def attach(src, tgt):

        if src in artifacts and tgt in node_ids:

            by_node[tgt].append(artifacts[src])

            if artifacts[src][0] == "Anotação":

                attached_notes.add(src)

        if tgt in artifacts and src in node_ids:

            by_node[src].append(artifacts[tgt])

            if artifacts[tgt][0] == "Anotação":

                attached_notes.add(tgt)



    for assoc in defs.findall(".//bpmn:association", NS):

        src = assoc.attrib.get("sourceRef")

        tgt = assoc.attrib.get("targetRef")

        attach(src, tgt)



    for dia in defs.findall(".//bpmn:dataInputAssociation", NS):

        srcs = [el.text for el in dia.findall("bpmn:sourceRef", NS) if el.text]

        tgt = dia.findtext("bpmn:targetRef", default="", namespaces=NS)

        for src in srcs:

            attach(src, tgt)



    for doa in defs.findall(".//bpmn:dataOutputAssociation", NS):

        srcs = [el.text for el in doa.findall("bpmn:sourceRef", NS) if el.text]

        tgt = doa.findtext("bpmn:targetRef", default="", namespaces=NS)

        for src in srcs:

            attach(src, tgt)



    orphan_notes = [artifacts[nid] for nid in annotations.keys() if nid not in attached_notes]

    if orphan_notes:

        by_node["_orphan_annotations_"] = orphan_notes



    return by_node





def rect_contains(rect, point):

    x, y, w, h = rect

    px, py = point

    return x <= px <= x + w and y <= py <= y + h





def rect_intersection_area(a, b):

    ax, ay, aw, ah = a

    bx, by, bw, bh = b

    x_overlap = max(0, min(ax + aw, bx + bw) - max(ax, bx))

    y_overlap = max(0, min(ay + ah, by + bh) - max(ay, by))

    return x_overlap * y_overlap





def infer_lane_by_di(nodes, node_lane, lane_name, node_bounds, lane_bounds):

    """Atribui lane via DI (interseccao de shapes ou centro)."""

    result = dict(node_lane)

    for node_id, rect in node_bounds.items():

        if node_id in result:

            continue  # ja mapeado por flowNodeRef

        overlaps = []

        for lane_id, lrect in lane_bounds.items():

            inter = rect_intersection_area(rect, lrect)

            if inter > 0:

                overlaps.append((inter, lrect[2] * lrect[3], lane_id))

        if overlaps:

            overlaps.sort(key=lambda t: (-t[0], t[1]))  # maior interseccao, depois menor area da lane

            top = [o for o in overlaps if o[0] == overlaps[0][0]]

            chosen = top[0][2]

            name = lane_name.get(chosen, "(ator nao identificado)")

            if len(top) > 1:

                name = f"{name} (ambiguo)"

            result[node_id] = name

            continue

        cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2

        candidates = []

        for lane_id, lrect in lane_bounds.items():

            if rect_contains(lrect, (cx, cy)):

                area = lrect[2] * lrect[3]

                candidates.append((area, lane_id))

        if candidates:

            candidates.sort(key=lambda t: t[0])  # menor area contendo

            chosen = candidates[0][1]

            name = lane_name.get(chosen, "(ator nao identificado)")

            if len(candidates) > 1:

                name = f"{name} (ambiguo)"

            result[node_id] = name

    return result





def format_number(parts):

    return ".".join(str(p) for p in parts)





def compare_parts(a, b):

    """Compara listas numéricas lexicograficamente."""

    for xa, xb in zip(a, b):

        if xa < xb:

            return -1

        if xa > xb:

            return 1

    if len(a) == len(b):

        return 0

    return -1 if len(a) < len(b) else 1





def describe_node(node):

    name = node.get("name") or ""

    task_kinds = {
        "task",
        "userTask",
        "serviceTask",
        "sendTask",
        "receiveTask",
        "manualTask",
    }

    if node.get("kind") in task_kinds:

        display = name or "(sem nome)"

        return f"Atividade: {display}"

    is_gateway = node["type"].startswith("Gateway")

    is_event = "Event" in node.get("kind", "")

    catch_throw = None

    if node.get("kind") == "intermediateCatchEvent":

        catch_throw = "captura"

    elif node.get("kind") == "intermediateThrowEvent":

        catch_throw = "disparo"

    if is_gateway and not name:

        return node["type"]

    display = name or "(sem nome)"

    if is_event:

        flavor = node.get("event_flavor") or ""

        if flavor == "link" and catch_throw:

            type_label = f"Evento intermediário (link, {catch_throw})"

        else:

            parts = [p for p in (flavor, catch_throw) if p]

            type_label = f"{node['type']} ({', '.join(parts)})" if parts else node["type"]

        return f"{type_label}: {display}"

    return f"{node['type']}: {display}"





def _clean_note(text: str) -> str:

    """Normaliza texto de anotação para linha única."""

    return " ".join((text or "").split())





def walk(node_id, numbering, nodes, flows, outgoing, incoming, node_lane, path_set, number_map, branch_state, artifacts):

    """DFS com numeração hierárquica; evita duplicar nós já descritos e corta loops no mesmo caminho."""

    lines = []

    node = nodes.get(node_id, {"type": "Elemento", "name": node_id})

    if node["type"] == "Elemento":

        return lines, numbering  # ignora nós desconhecidos

    indent = "    " * (len(numbering) - 1)

    detail_indent = indent + "    "

    num_str = format_number(numbering)



    if node_id in number_map:

        prev = number_map[node_id]

        cmp = compare_parts(prev["parts"], numbering)

        if cmp < 0:

            label = "retorna para"

        elif cmp > 0:

            label = "avança para"

        else:

            label = "referência"

        lines.append(f"{indent}({label} {prev['num_str']})")

        return lines, numbering



    if node_id in path_set:

        lines.append(f"{indent}(loop em {num_str})")

        return lines, numbering



    outs = outgoing.get(node_id, [])

    is_gateway = node["type"].startswith("Gateway")

    is_diverging_gateway = is_gateway and len(outs) > 1

    is_converging_gateway = is_gateway and len(incoming.get(node_id, [])) > 1 and len(outs) == 1 and not is_diverging_gateway

    is_parallel_convergence = is_converging_gateway and node.get("kind") == "parallelGateway"



    # Se for gateway apenas de convergência (exceto paralelos), não imprime linha; passa adiante

    if is_converging_gateway and outs and not is_parallel_convergence:

        number_map[node_id] = {"num_str": num_str, "parts": numbering}

        new_path = path_set | {node_id}

        next_id = flows[outs[0]]["target"]

        child_lines, last_num = walk(

            next_id,

            numbering,

            nodes,

            flows,

            outgoing,

            incoming,

            node_lane,

            new_path,

            number_map,

            branch_state,

            artifacts,

        )

        lines.extend(child_lines)

        return lines, last_num



    prefix = f"{indent}{num_str}. "

    desc = describe_node(node)

    detail_indent = indent + "    "

    if is_parallel_convergence:

        desc = "Fim do Gateway Paralelo (convergência)"

    lines.append(f"{prefix}{desc}")

    task_kinds = {

        "task": "Sem tipo",

        "userTask": "Atividade de Usuário",

        "serviceTask": "Atividade de Serviço",

        "sendTask": "Atividade de Envio",

        "receiveTask": "Atividade de Recebimento",

        "manualTask": "Atividade Manual",

    }

    if node.get("kind") in task_kinds:

        actor = node_lane.get(node_id, "(ator nao identificado)")

        type_label = task_kinds[node["kind"]]

        lines.append(f"{detail_indent}Ator: {actor} | Tipo: {type_label}")

    elif node.get("kind") in {"subProcess", "callActivity"}:

        actor = node_lane.get(node_id, "(ator nao identificado)")

        lines.append(f"{detail_indent}Ator: {actor}")



    docs = sorted({text for label, text in artifacts.get(node_id, []) if label == "Documento"})

    systems = sorted({text for label, text in artifacts.get(node_id, []) if label == "Sistema"})

    notes = []

    seen_notes = set()

    for label, text in artifacts.get(node_id, []):

        if label == "Anotação":

            key = _clean_note(text)

            if key and key not in seen_notes:

                seen_notes.add(key)

                notes.append(key)

    if docs or systems:

        info_indent = indent + "    "

        parts = []

        if systems:

            parts.append(f"Sistema: {', '.join(systems)}")

        if docs:

            parts.append(f"Documento: {', '.join(docs)}")

        lines.append(f"{info_indent}{' | '.join(parts)}")

    if notes:

        info_indent = indent + "    "

        for text in notes:
            lines.append(f'{info_indent}Anotação: "{text}"')



    number_map[node_id] = {"num_str": num_str, "parts": numbering}

    new_path = path_set | {node_id}



    last_used = numbering



    if is_diverging_gateway:

        state = branch_state.setdefault(node_id, {"next": 1})

        for branch_idx, flow_id in enumerate(outs, start=1):

            child_num = state["next"]

            state["next"] += 1

            flow = flows[flow_id]

            child = flow["target"]

            if not flow["name"] and node.get("kind") == "parallelGateway":

                branch = f"Caminho {branch_idx:02d}"

            else:

                branch = flow["name"] or f"Caminho {child_num}"

            branch_indent = indent + "    "

            lines.append(f"{branch_indent}Caso {branch}:")

            child_lines, last_num = walk(

                child,

                numbering + [child_num, 1],

                nodes,

                flows,

                outgoing,

                incoming,

                node_lane,

                new_path,

                number_map,

                branch_state,

                artifacts,

            )

            lines.extend(child_lines)

            last_used = last_num

            if len(last_num) > len(numbering):

                suffix = last_num[len(numbering)]

                state["next"] = max(state["next"], suffix + 1)

    elif len(outs) == 1:

        next_id = flows[outs[0]]["target"]

        next_number = numbering[:-1] + [numbering[-1] + 1]

        child_lines, last_num = walk(

            next_id,

            next_number,

            nodes,

            flows,

            outgoing,

            incoming,

            node_lane,

            new_path,

            number_map,

            branch_state,

            artifacts,

        )

        lines.extend(child_lines)

        last_used = last_num



    return lines, last_used





def render_bpmn(path: Path) -> str:

    tree = ET.parse(path)

    defs = tree.getroot()

    processes = defs.findall("bpmn:process", NS)

    if not processes:

        raise ValueError("Nenhum processo encontrado no BPMN.")



    participant_by_proc: Dict[str, str] = {}

    participant_by_id: Dict[str, str] = {}

    orphan_annotations: List[Tuple[str, str]] = []

    proc_info = []

    all_node_ids = set()

    for collab in defs.findall("bpmn:collaboration", NS):

        for part in collab.findall("bpmn:participant", NS):

            pref = part.attrib.get("processRef")

            pid = part.attrib.get("id")

            if pref:

                participant_by_proc[pref] = part.attrib.get("name", "").strip()

            if pid:

                participant_by_id[pid] = part.attrib.get("name", "").strip() or participant_by_proc.get(pref, "")



    for proc in processes:

        nodes, flows, outgoing, incoming = collect_elements(proc)

        proc_info.append((proc, nodes, flows, outgoing, incoming))

        all_node_ids.update(nodes.keys())



    artifacts_global = collect_artifacts(defs, all_node_ids)

    orphan_annotations = artifacts_global.pop("_orphan_annotations_", [])



    node_to_pool: Dict[str, str] = {}

    node_meta: Dict[str, Tuple[str, Dict[str, str]]] = {}

    all_lines = []

    msg_lines: List[str] = []

    for proc, nodes, flows, outgoing, incoming in proc_info:

        for nid in nodes.keys():

            node_to_pool[nid] = proc.attrib.get("id", "")

            node_meta[nid] = ("", nodes[nid])

        node_lane_map, lane_name = collect_lanes(proc)

        node_bounds, lane_bounds = collect_di_bounds(defs, set(nodes.keys()), set(lane_name.keys()))

        node_lane = infer_lane_by_di(nodes, node_lane_map, lane_name, node_bounds, lane_bounds)

        artifacts = artifacts_global



        start_events = [e.attrib["id"] for e in proc.findall("bpmn:startEvent", NS)]

        if not start_events:

            continue



        title = proc.attrib.get("name") or participant_by_proc.get(proc.attrib.get("id"), "") or path.stem

        for nid in nodes.keys():

            node_meta[nid] = (title, nodes[nid])

        lines = [f"Titulo: {title}"]

        for idx, start_id in enumerate(start_events, start=1):

            branch_lines, _last = walk(

                start_id,

                [idx],

                nodes,

                flows,

                outgoing,

                incoming,

                node_lane,

                set(),

                {},

                {},

                artifacts,

            )

            lines.extend(branch_lines)

        all_lines.extend(lines)

        all_lines.append("")  # separador entre pools



    for collab in defs.findall("bpmn:collaboration", NS):

        for mf in collab.findall("bpmn:messageFlow", NS):

            src = mf.attrib.get("sourceRef")

            tgt = mf.attrib.get("targetRef")

            if not src or not tgt:

                continue

            src_proc = node_to_pool.get(src, "")

            tgt_proc = node_to_pool.get(tgt, "")

            src_pool_name = participant_by_id.get(src) or participant_by_proc.get(src_proc, src_proc or "")

            tgt_pool_name = participant_by_id.get(tgt) or participant_by_proc.get(tgt_proc, tgt_proc or "")

            if src in node_meta:

                pool_title, meta = node_meta[src]

                src_pool_name = src_pool_name or pool_title

                src_elem = meta.get("name") or meta.get("type")

            else:

                src_elem = src

            if tgt in node_meta:

                pool_title, meta = node_meta[tgt]

                tgt_pool_name = tgt_pool_name or pool_title

                tgt_elem = meta.get("name") or meta.get("type")

            else:

                tgt_elem = tgt

            src_label = f"{src_pool_name or src_proc}:{src_elem}"

            tgt_label = f"{tgt_pool_name or tgt_proc}:{tgt_elem}"

            mf_name = mf.attrib.get("name", "").strip() or "(sem nome)"

            msg_lines.append((src_pool_name, src_elem, tgt_pool_name, tgt_elem, mf_name))



    if msg_lines:

        all_lines.append("Interações entre processos (message flows):")

        all_lines.append("- Origem (Processo / Elemento) | Destino (Processo / Elemento) | Mensagem")

        for src_pool_name, src_elem, tgt_pool_name, tgt_elem, mf_name in msg_lines:

            src_desc = f"{src_pool_name} / {src_elem}"

            tgt_desc = f"{tgt_pool_name} / {tgt_elem}"

            all_lines.append(f"- {src_desc} | {tgt_desc} | {mf_name}")



    if orphan_annotations:

        all_lines.append("")

        all_lines.append("Anotações não ligadas a elementos:")

        seen = set()

        for _label, text in orphan_annotations:

            key = _clean_note(text)

            if key and key not in seen:

                seen.add(key)

                all_lines.append(f'- "{key}"')



    return "\n".join(all_lines).rstrip()





def pick_bpmn_from_folder(base: Path) -> Path:

    """Lista BPMN no diretório base e permite escolher pelo índice."""

    candidates: List[Path] = sorted(base.glob("*.bpmn"))

    if not candidates:

        raise SystemExit(f"Nenhum arquivo .bpmn encontrado em {base}")

    print("Selecione o BPMN:")

    for idx, p in enumerate(candidates, start=1):

        print(f"{idx}. {p.name}")

    try:

        choice = input("Número do BPMN: ").strip()

    except EOFError:

        choice = "1"

    if not choice.isdigit() or not (1 <= int(choice) <= len(candidates)):

        raise SystemExit("Seleção inválida.")

    return candidates[int(choice) - 1]





def main():

    if len(sys.argv) > 1:

        bpmn_path = Path(sys.argv[1])

    else:

        base = Path(__file__).resolve().parent.parent

        bpmn_path = pick_bpmn_from_folder(base)

    if not bpmn_path.exists():

        raise SystemExit(f"Arquivo BPMN nao encontrado: {bpmn_path}")

    print(render_bpmn(bpmn_path))





if __name__ == "__main__":

    main()









def render_bpmn_bytes(content: bytes, filename: str = "arquivo") -> str:

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".bpmn") as tmp:

        tmp.write(content)

        tmp_path = Path(tmp.name)

    try:

        return render_bpmn(tmp_path)

    finally:

        try:

            tmp_path.unlink()

        except FileNotFoundError:

            pass

