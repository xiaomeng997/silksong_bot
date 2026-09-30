using System;
using System.Collections.Generic;
using HutongGames.PlayMaker;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// RPC "fsm.graph" (DESIGN §4.6 get_fsm_graph): the static structure of a live PlayMaker FSM, for building
    /// behaviour tables offline from the "fsm" event stream. Args: iid (GameObject instance id, as in "ents" and
    /// "fsm" events) and/or obj (GameObject name or type_key), optional fsm (FSM name). Returns one graph when
    /// fsm is given, else the list of graphs of every FSM on the first matching object:
    ///   {iid, obj, fsm, template, start, active, states: [{name, transitions {event: to}, actions [type] | nil}],
    ///    global {event: to}, events [name], vars {float|int|bool|string: {name: value}}}
    /// </summary>
    internal static class FsmGraph
    {
        public static object Handle(Dictionary<string, object> args)
        {
            var iid = (int)Ipc.Rpc.Long(args, "iid");
            var obj = Ipc.Rpc.Str(args, "obj");
            var fsmName = Ipc.Rpc.Str(args, "fsm");
            if (iid == 0 && obj == null) throw new ArgumentException("fsm.graph needs iid or obj");

            var go = iid != 0 ? EntityRegistry.FindGo(iid) : null;
            if (go == null)
            {
                // Enabled FSMs only; disabled components are reachable through an entity iid above.
                foreach (var f in PlayMakerFSM.FsmList)
                {
                    if (f == null) continue;
                    var fgo = f.gameObject;
                    if (iid != 0 ? fgo.GetInstanceID() != iid : !NameMatches(fgo.name, obj)) continue;
                    go = fgo;
                    break;
                }
            }
            if (go == null) throw new InvalidOperationException($"no object with FSMs matches iid={iid} obj={obj}");

            var graphs = new List<object>();
            foreach (var f in go.GetComponents<PlayMakerFSM>())
            {
                var fsm = EntityRegistry.FsmOf(f);
                if (fsm == null) continue;
                if (fsmName != null && fsm.Name != fsmName) continue;
                var g = Graph(go, f, fsm);
                if (fsmName != null) return g;
                graphs.Add(g);
            }
            if (fsmName != null) throw new InvalidOperationException($"'{go.name}' has no FSM named '{fsmName}'");
            return graphs;
        }

        private static bool NameMatches(string name, string wanted) =>
            name == wanted || EntityRegistry.TypeKey(name) == wanted;

        private static Dictionary<string, object> Graph(GameObject go, PlayMakerFSM f, Fsm fsm)
        {
            var states = new List<object>();
            foreach (var st in fsm.States ?? new FsmState[0])
            {
                List<object> actions = null;
                // FsmState.Actions logs an error for a state whose Fsm is not set; such FSMs are not initialized.
                if (st.IsInitialized)
                {
                    actions = new List<object>();
                    foreach (var a in st.Actions)
                        actions.Add(a?.GetType().Name);
                }
                states.Add(new Dictionary<string, object>
                {
                    ["name"] = st.Name,
                    ["transitions"] = Transitions(st.Transitions),
                    ["actions"] = actions,
                });
            }
            var events = new List<object>();
            foreach (var e in fsm.Events ?? new FsmEvent[0])
                events.Add(e?.Name);

            var vars = fsm.Variables;
            var floats = new Dictionary<string, object>();
            foreach (var v in vars.FloatVariables) floats[v.Name] = v.Value;
            var ints = new Dictionary<string, object>();
            foreach (var v in vars.IntVariables) ints[v.Name] = v.Value;
            var bools = new Dictionary<string, object>();
            foreach (var v in vars.BoolVariables) bools[v.Name] = v.Value;
            var strings = new Dictionary<string, object>();
            foreach (var v in vars.StringVariables) strings[v.Name] = v.Value;

            return new Dictionary<string, object>
            {
                ["iid"] = go.GetInstanceID(),
                ["obj"] = go.name,
                ["fsm"] = fsm.Name,
                ["template"] = HitboxCategory.TemplateName(f),
                ["start"] = fsm.StartState,
                ["active"] = fsm.ActiveStateName,
                ["states"] = states,
                ["global"] = Transitions(fsm.GlobalTransitions),
                ["events"] = events,
                ["vars"] = new Dictionary<string, object> { ["float"] = floats, ["int"] = ints, ["bool"] = bools, ["string"] = strings },
            };
        }

        /// <summary>event name -> target state. PlayMaker allows one transition per event per state; a transition
        /// without an event (never fired) is keyed "".</summary>
        private static Dictionary<string, object> Transitions(FsmTransition[] transitions)
        {
            var map = new Dictionary<string, object>();
            if (transitions == null) return map;
            foreach (var t in transitions)
            {
                if (t == null) continue;
                map[t.FsmEvent?.Name ?? ""] = t.ToState;
            }
            return map;
        }
    }
}
