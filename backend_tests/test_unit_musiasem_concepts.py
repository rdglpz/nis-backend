import unittest

import backend.common.helper
from backend.model.memory.expressions import ExpressionsEngine
from backend.model.memory.musiasem_concepts import *
from backend.model.memory.musiasem_concepts_helper import *
from backend.model.memory.musiasem_concepts_helper import _get_observer, _obtain_relation

""" Integration tests for in memory model structures """


def setUpModule():
    print('In setUpModule()')


def tearDownModule():
    print('In tearDownModule()')


def prepare_partial_key_dictionary():
    glb_idx = PartialRetrievalDictionary()

    oer = Observer("tester")
    p0 = Processor("A1")
    p1 = Processor("A2")
    p2 = Processor("B")
    p3 = Processor("C")
    glb_idx.put(p0.key(), p0)
    glb_idx.put(p1.key(), p1)
    glb_idx.put(p2.key(), p2)
    glb_idx.put(p3.key(), p3)
    obs = ProcessorsRelationPartOfObservation(p0, p2, oer)
    glb_idx.put(obs.key(), obs)
    obs = ProcessorsRelationPartOfObservation(p1, p2, oer)
    glb_idx.put(obs.key(), obs)
    obs = ProcessorsRelationPartOfObservation(p2, p3, oer)
    glb_idx.put(obs.key(), obs)
    return glb_idx


def prepare_simple_processors_hierarchy():
    state = State()
    p1,_,_ = find_or_create_observable(state, "P1", "test_observer",
                                   aliases=None,
                                   proc_external=None, proc_attributes=None, proc_location=None,
                                   fact_roegen_type=None, fact_attributes=None,
                                   fact_incoming=None, fact_external=None, fact_location=None
                                   )
    p2,_,_ = find_or_create_observable(state, "P1.P2", "test_observer",
                                   aliases=None,
                                   proc_external=None, proc_attributes=None, proc_location=None,
                                   fact_roegen_type=None, fact_attributes=None,
                                   fact_incoming=None, fact_external=None, fact_location=None
                                   )
    p3,_,_ = find_or_create_observable(state, "P3", "test_observer",
                                   aliases=None,
                                   proc_external=None, proc_attributes=None, proc_location=None,
                                   fact_roegen_type=None, fact_attributes=None,
                                   fact_incoming=None, fact_external=None, fact_location=None
                                   )
    p4,_,_ = find_or_create_observable(state, "P1.P2.P3", "test_observer",
                                   aliases=None,
                                   proc_external=None, proc_attributes=None, proc_location=None,
                                   fact_roegen_type=None, fact_attributes=None,
                                   fact_incoming=None, fact_external=None, fact_location=None
                                   )
    p5,_,_ = find_or_create_observable(state, "P1.P2b", "test_observer",
                                   aliases=None,
                                   proc_external=None, proc_attributes=None, proc_location=None,
                                   fact_roegen_type=None, fact_attributes=None,
                                   fact_incoming=None, fact_external=None, fact_location=None
                                   )
    return state


class ModelBuildingHierarchies(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print('In setUpClass()')
        cls.good_range = range(1, 10)

    @classmethod
    def tearDownClass(cls):
        print('In tearDownClass()')
        del cls.good_range

    def setUp(self):
        super().setUp()
        print('\nIn setUp()')

    def tearDown(self):
        print('In tearDown()')
        super().tearDown()

    # ###########################################################

    def test_001_hierarchy(self):
        h = Heterarchy("Test")
        t1 = Taxon("T1", None, h)
        t2 = Taxon("T2", t1, h)
        t3 = Taxon("T3", None, h)
        roots = [t1, t3]
        h.roots_append(roots)
        # Same roots
        self.assertEqual(len(set(roots).intersection(h.roots)), len(roots))
        # Relations
        self.assertEqual(t1.get_children(h)[0], t2)
        self.assertEqual(t2.parent, t1)  # Special test, to test parent of node in a single hierarchy
        self.assertEqual(t3.get_parent(h), None)

    def test_002_hierarchy_2(self):
        h = build_hierarchy("Test_auto", "Taxon", None, {"T1": {"T2": None}, "T3": None})
        self.assertEqual(len(h.roots), 2)

    def test_003_hierarchy_of_factors(self):
        h = Heterarchy("Test2")
        f1 = FactorType("F1", None, h)
        f2 = FactorType("F2", f1, h)
        t1 = Taxon("T1")
        with self.assertRaises(Exception):
            FactorType("F3", t1)
        f3 = FactorType("F3", None, h)
        roots = [f1, f3]
        h.roots_append(roots)
        # Same roots
        self.assertEqual(len(set(roots).intersection(h.roots)), len(roots))
        # Relations
        self.assertEqual(f1.get_children(h)[0], f2)
        self.assertEqual(f2.get_parent(h), f1)
        self.assertEqual(f3.get_parent(h), None)

    def test_004_hierarchy_of_processors(self):
        state = prepare_simple_processors_hierarchy()
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        p2 = glb_idx.get(Processor.partial_key("P1.P2"))[0]
        p4 = glb_idx.get(Processor.partial_key("P1.P2.P3"))[0]
        p5 = glb_idx.get(Processor.partial_key("P1.P2b"))[0]
        names = p2.full_hierarchy_names(glb_idx)
        self.assertEqual(names[0], "P1.P2")
        # Make "p1.p2.p3" processor descend from "p1.p2b" so it will be also "p1.p2b.p3"
        r = _obtain_relation(p5, p4, RelationClassType.pp_part_of, "test_observer", None, state)
        names = p4.full_hierarchy_names(glb_idx)
        self.assertEqual(names[0], "P1.P2.P3")

        # TODO Register Aliases for the Processor (in "obtain_relation")

    def test_005_hierarchy_of_processors_after_serialization_deserialization(self):
        state = prepare_simple_processors_hierarchy()
        # Serialize, deserialize
        s = state.serialize()
        state = State.deserialize(s)
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        p2 = glb_idx.get(Processor.partial_key("P1.P2"))[0]
        p4 = glb_idx.get(Processor.partial_key("P1.P2.P3"))[0]
        p5 = glb_idx.get(Processor.partial_key("P1.P2b"))[0]

        names = p2.full_hierarchy_names(glb_idx)
        self.assertEqual(names[0], "P1.P2")
        # Make "p1.p2.p3" processor descend from "p1.p2b" so it will be also "p1.p2b.p3"
        r = _obtain_relation(p5, p4, RelationClassType.pp_part_of, "test_observer", None, state)
        names = p4.full_hierarchy_names(glb_idx)
        self.assertEqual(names[0], "P1.P2.P3")

        # TODO Register Aliases for the Processor (in "obtain_relation")


class ModelBuildingQuantativeObservations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    def test_001_soslaires_windfarm_observations(self):
        state = State()
        k = {"spread": None, "assessment": None, "pedigree": None, "pedigree_template": None,
             "relative_to": None,
             "time": None,
             "geolocation": None,
             "comments": None,
             "tags": None,
             "other_attributes": None,
             "proc_aliases": None,
             "proc_external": False,
             "proc_location": None,
             "proc_attributes": None,
             "ftype_roegen_type": FlowFundRoegenType.fund,
             "ftype_attributes": None,
             "fact_incoming": True,
             "fact_external": None,
             "fact_location": None
             }
        create_quantitative_observation(state, "WindFarm:LU.cost", "17160", "€", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:HA.cost", "1800", "€", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:PC.cost", "85600", "€", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:LU", "8800", "m2", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:HA", "660", "hours", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:PC", "2.64", "MW", **(k.copy()))
        k["ftype_roegen_type"] = FlowFundRoegenType.flow
        create_quantitative_observation(state, "WindFarm:WindElectricity", "9.28", "GWh", **(k.copy()))
        create_quantitative_observation(state, "WindFarm:WindElectricity.max_production", "23.2", "GWh", **(k.copy()))
        k["proc_external"] = True
        create_quantitative_observation(state, "ElectricGrid:GridElectricity", "6.6", "GWh", **(k.copy()))
        # ============================= READS AND ASSERTIONS =============================
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        # Check function "get_factor_or_processor_or_factor_type"
        wf = find_observable("WindFarm", glb_idx) # Get a Processor
        self.assertIsInstance(wf, Processor)
        wf = find_observable("WindFarm:", glb_idx) # Get a Processor
        self.assertIsInstance(wf, Processor)
        lu = find_observable(":LU", glb_idx) # Get a FactorType
        self.assertIsInstance(lu, FactorType)
        wf_lu = find_observable("WindFarm:LU", glb_idx) # Get a Factor, using full name
        self.assertIsInstance(wf_lu, Factor)
        wf_lu = find_observable(":LU", glb_idx, processor=wf) # Get a Factor, using already known Processor
        self.assertIsInstance(wf_lu, Factor)
        wf_lu = find_observable("WindFarm:", glb_idx, factor_type=lu) # Get a Factor, using already known FactorType
        self.assertIsInstance(wf_lu, Factor)
        # Check things about the Factor
        self.assertEqual(wf_lu.processor.name, "WindFarm")
        self.assertEqual(wf_lu.taxon.name, "LU")
        self.assertEqual(wf_lu.name, "LU")
        # Get observations from the Factor
        obs = glb_idx.get(FactorQuantitativeObservation.partial_key(wf_lu))
        self.assertEqual(len(obs), 1)
        # Get observations from the Observer
        oer = _get_observer(Observer.no_observer_specified, glb_idx)
        obs = glb_idx.get(FactorQuantitativeObservation.partial_key(observer=oer))
        self.assertEqual(len(obs), 9)  # NINE !!!!
        # Get observations from both Factor and Observer
        obs = glb_idx.get(FactorQuantitativeObservation.partial_key(factor=wf_lu, observer=oer))
        self.assertEqual(len(obs), 1)


class ModelBuildingRelationObservations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    def test_001_build_soslaires_relations(self):
        backend.common.helper.case_sensitive = False
        state = State()
        create_relation_observations(state, "WindFarm:WindElectricity", ["DesalinationPlant", ("ElectricGrid")])
        create_relation_observations(state, "ElectricGrid", "DesalinationPlant:GridElectricity")
        create_relation_observations(state, "DesalinationPlant:DesalinatedWater", "Farm:BlueWater")
        crop_processors = ["Cantaloupe", "Watermelon", "Tomato", "Zucchini", "Beans", "Pumpkin", "Banana", "Moringa"]
        create_relation_observations(state, "Farm", crop_processors, RelationClassType.pp_part_of)
        crop_processors = ["Farm."+p for p in crop_processors]
        create_relation_observations(state, "Farm:LU", crop_processors)
        create_relation_observations(state, "Farm:HA", crop_processors)
        create_relation_observations(state, "Farm:IrrigationCapacity", crop_processors)
        create_relation_observations(state, "Farm:BlueWater", crop_processors)
        create_relation_observations(state, "Farm:Agrochemicals", crop_processors)
        create_relation_observations(state, "Farm:Fuel", crop_processors)
        create_relation_observations(state, "Farm:GreenWater", crop_processors, RelationClassType.ff_reverse_directed_flow)
        create_relation_observations(state, "Farm:MaterialWaste", crop_processors, RelationClassType.ff_reverse_directed_flow)
        create_relation_observations(state, "Farm:DiffusivePollution", crop_processors, RelationClassType.ff_reverse_directed_flow)
        create_relation_observations(state, "Farm:CO2", crop_processors, RelationClassType.ff_reverse_directed_flow)
        create_relation_observations(state, "Farm:Vegetables", [p + ":Vegetables." + p for p in crop_processors], RelationClassType.ff_reverse_directed_flow)
        # ============================= READS AND ASSERTIONS =============================
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        # Check Observables and FlowTypes existence
        processors = glb_idx.get(Processor.partial_key(None))
        self.assertEqual(len(processors), 12)
        dplant = glb_idx.get(Processor.partial_key("desalinationplant"))
        farm = glb_idx.get(Processor.partial_key("farm"))
        banana = glb_idx.get(Processor.partial_key("farm.banana"))
        lu = glb_idx.get(FactorType.partial_key("lU"))
        farm_lu = glb_idx.get(Factor.partial_key(processor=farm[0], taxon=lu[0]))

        # Check Relations between observables
        rels = glb_idx.get(FactorsRelationDirectedFlowObservation.partial_key(source=farm_lu[0]))
        self.assertEqual(len(rels), 8)


class ModelBuildingProcessors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    # ###########################################################
    def test_001_processor_hierarchical_names_from_part_of_relations(self):
        prd = prepare_partial_key_dictionary()

        p = prd.get(Processor.partial_key("C"))
        self.assertEqual(len(p), 1)
        p = p[0]  # Get the processor
        n = p.full_hierarchy_names(prd)
        self.assertEqual(len(n), 2)

    def test_tagged_processors(self):
        # Create a taxonomy
        h = build_hierarchy("Test_auto", "Taxon", None, {"T1": {"T2": None}, "T3": None})
        # Create a processor and tag it
        p1 = Processor("P1")
        t1 = h.get_node("T1")
        t2 = h.get_node("T2")
        p1.tags_append(t1)
        self.assertTrue(t1 in p1.tags)
        self.assertFalse(t2 in p1.tags)
        p1.tags_append(t2)
        # Check if the processor meets the tags
        self.assertTrue(t1 in p1.tags)
        self.assertTrue(t2 in p1.tags)
        self.assertFalse(h.get_node("T3") in p1.tags)

    def test_processor_with_attributes(self):
        # Create a Processor
        p1 = Processor("P1")
        # Create a Location
        geo = Geolocation("Spain")
        # Assign it as "location" attribute
        p1.attributes_append("location", geo)
        # Check
        self.assertEqual(p1.attributes["location"], geo)

    def test_processors_with_factors(self):
        """ Processors adorned with factors. No need for connections.
            Need to specify if input and other. Only Funds do not need this specification
        """
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create a processor
        p1 = Processor("P1")
        # Create a Factor and append it to the Processor (¿register it into the FactorType also?)
        f = Factor("", p1, FactorInProcessorType(external=False, incoming=True), ft.get_node("F1"))
        p1.factors_append(f)
        # Check that the processor contains the Factor
        self.assertTrue(f in p1.factors)


class ModelBuildingFactors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    # ###########################################################

    def test_sequentially_connected_factors(self):
        """ Two or more processors, with factors. Connect some of them """
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create two Processors, same level
        ps = build_hierarchy("Procs", "Processor", None, {"P1": None, "P2": None})
        # Create a Factor for each processor
        f1 = Factor("", ps.get_node("P1"), FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        f2 = Factor("", ps.get_node("P2"), FactorInProcessorType(external=False, incoming=True), ft.get_node("F1"))
        # Connect from one to the other
        c = f1.connect_to(f2)
        # Check that the connection exists in both sides, and that it is sequential
        self.assertTrue(c in f1.connections)
        self.assertTrue(c in f2.connections)
        self.assertFalse(c.hierarchical)

    def test_hierarchically_connected_factors(self):
        """ Two or more processors, with factors. Connect some of them """
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create two Processors, parent and child
        ps = build_hierarchy("Procs", "Processor", None, {"P1": {"P2": None}})
        # Create a Factor for each processor
        f1 = Factor.create("", ps.get_node("P1"), FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        f2 = Factor.create("", ps.get_node("P2"), FactorInProcessorType(external=False, incoming=True), ft.get_node("F1"))
        # Connect from one to the other
        c = f1.connect_to(f2, ps)
        # Check that the connection exists in both sides, and that it is Hierarchical
        self.assertTrue(c in f1.connections)
        self.assertTrue(c in f2.connections)
        self.assertTrue(c.hierarchical)

    def test_hybrid_connected_factors(self):
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create Three Processors, parent and child, and siblings
        ps = build_hierarchy("Procs", "Processor", None, {"P1": {"P2": None}, "P3": None})
        # Create a Factor for each processor, and an additional factor for the processor which is parent and sibling
        f11 = Factor.create("", ps.get_node("P1"), FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        f2 = Factor.create("", ps.get_node("P2"), FactorInProcessorType(external=False, incoming=True), ft.get_node("F1"))
        f12 = Factor.create("", ps.get_node("P1"), FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        f3 = Factor.create("", ps.get_node("P3"), FactorInProcessorType(external=False, incoming=True), ft.get_node("F1"))
        # Do the connections
        ch = f11.connect_to(f2, ps)
        cs = f12.connect_to(f3, ps)
        # Check each connection
        self.assertTrue(ch in f11.connections)
        self.assertTrue(ch in f2.connections)
        self.assertTrue(cs in f12.connections)
        self.assertTrue(cs in f3.connections)
        self.assertTrue(ch.hierarchical)
        self.assertFalse(cs.hierarchical)

    def test_create_qq(self):
        # Create a value with incorrect unit
        with self.assertRaises(Exception) as ctx:
            QualifiedQuantityExpression.nu(5, "non existent unit")

        q2 = QualifiedQuantityExpression.nu(5, "m²")

    def test_processors_with_factors_with_one_observation(self):
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create a processor
        p1 = Processor("P1")
        # Create a Factor and assign it to the Processor
        f1 = Factor.create("", p1, FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        # Observer of the Value
        oer = Observer("oer1")
        # Create an Observation with its value
        fo = FactorQuantitativeObservation(QualifiedQuantityExpression.nu(5, "m²"), oer, f1)
        # Assign to the factor
        f1.observations_append(fo)
        # Check
        self.assertTrue(fo in f1.observations)

    def test_processors_with_factors_with_more_than_one_observation(self):
        # Create a Hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Create a processor
        p1 = Processor("P1")
        # Create a Factor and assign it to the Processor
        f1 = Factor.create("", p1, FactorInProcessorType(external=False, incoming=False), ft.get_node("F1"))
        # Observer of the Value
        oer1 = Observer("oer1")
        oer2 = Observer("oer2")
        # Create a Value
        fo1 = FactorQuantitativeObservation.create_and_append(QualifiedQuantityExpression.nu(5, "m²"), f1, oer1)
        fo2 = FactorQuantitativeObservation.create_and_append(QualifiedQuantityExpression.nu(5, "m²"), f1, oer2)
        f1.observations_append(fo1)
        f1.observations_append(fo2)
        # Check
        self.assertTrue(fo1 in f1.observations)
        self.assertTrue(fo2 in f1.observations)


class ModelBuildingExpressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    # ###########################################################

    def test_processors_with_expression_in_taxonomy(self):
        # A hierarchy of Taxon
        h = build_hierarchy("H1", "Taxon", None, {"T1": {"T2": None}, "T3": None})
        # A taxon is a function of others
        t3 = h.get_node("T3")
        t3.expression = {"op": "*", "oper": [{"n": 0.5}, {"v": "T1"}]}
        t2 = h.get_node("T2")
        t2.expression = {"n": 3, "u": "kg"}
        # INJECT EXPRESSIONS into the ExpEvaluator:
        expev = ExpressionsEngine()
        expev.append_expressions({"lhs": {"v": "H1.T1"}, "rhs": {"v": "H1.T2"}})  # t1 = t2
        expev.append_expressions({"lhs": {"v": "H1.T3"}, "rhs": {"op": "*", "oper": [{"n": 0.5}, {"v": "H1.T1"}]}})  # t3 = 0.5*t1
        expev.append_expressions({"lhs": {"v": "H1.T2"}, "rhs": {"n": 3, "u": "kg"}})  # t2 = 3 kg
        expev.cascade_solver()
        self.assertEqual(expev.variables["H1.T1"].values[0][0], ureg("3 kg"))
        self.assertEqual(expev.variables["H1.T2"].values[0][0], ureg("3 kg"))
        self.assertEqual(expev.variables["H1.T3"].values[0][0], ureg("1.5 kg"))
        # TODO Check: cascade up to T1
        expev.reset()
        #expev.r
        # TODO Check: cascade side to T3

    def test_processors_with_factors_with_expression_observation(self):
        # A hierarchy of FactorType
        ft = build_hierarchy("Taxs", "FactorType", None, {"F1": None, "F2": None})
        # Hierarchy of Processors
        ps = build_hierarchy("Procs", "Processor", None, {"P1": {"P2": None, "P4": None}, "P3": None})
        # Attach Factor
        #connect_processors(source_p: Processor, dest_p: Processor, h: "Hierarchy", weight: float, taxon: FactorType, source_name: str = None, dest_name: str = None)
        # TODO A taxon is a function of others

        pass

    def test_processors_with_factors_with_more_than_expression_observation(self):
        pass


class ModelBuildingWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    # ###########################################################

    def test_register_entities(self):
        """ Create context.
            Register hierarchies, processors. Check no double registration is done
        """

    def test_connect_processors_using_registry(self):
        pass

    def test_build_hierarchy_using_registry(self):
        pass

    def test_import(self):
        # TODO Create a Space context
        # TODO Create a FactorType Hierarchy
        # TODO Close Space context
        # TODO Create another space context
        # TODO
        pass


class ModelSolvingExpressionsEvaluationSimple(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    """ Build simple models including all types of expression """


class ModelBuildingIndicatorsSimple(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        pass

    def tearDown(self):
        pass
        super().tearDown()

    # ###########################################################

    def test_intensive_processor_to_extensive(self):
        pass


if __name__ == '__main__':
    unittest.main()