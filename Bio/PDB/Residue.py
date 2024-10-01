# Copyright (C) 2002, Thomas Hamelryck (thamelry@binf.ku.dk)
#
# This file is part of the Biopython distribution and governed by your
# choice of the "Biopython License Agreement" or the "BSD 3-Clause License".
# Please see the LICENSE file that should have been included as part of this
# package.

"""Residue class, used by Structure objects."""

from typing import TYPE_CHECKING
from typing import TypeVar

from Bio.PDB.Entity import DisorderedEntityWrapper
from Bio.PDB.Entity import Entity
from Bio.PDB.PDBExceptions import PDBConstructionException
from Bio.PDB.rotamers import CHI_ANGLES, RESIDUE_ORDER
from Bio.PDB.vectors import calc_dihedral, Vector, rotaxis2m
from Bio.PDB.Atom import Atom

import numpy as np

if TYPE_CHECKING:
    from Bio.PDB.Chain import Chain

_ResidueT = TypeVar("_ResidueT", bound="Residue")


_atom_name_dict = {}
_atom_name_dict["N"] = 1
_atom_name_dict["CA"] = 2
_atom_name_dict["C"] = 3
_atom_name_dict["O"] = 4


class Residue(Entity["Chain", "Atom"]):
    """Represents a residue. A Residue object stores atoms."""

    def __init__(self, id, resname, segid):
        """Initialize the class."""
        self.level = "R"
        self.disordered = 0
        self.resname = resname
        self.segid = segid
        self.internal_coord = None
        Entity.__init__(self, id)

    def __repr__(self):
        """Return the residue full id."""
        resname = self.get_resname()
        hetflag, resseq, icode = self.get_id()
        full_id = (resname, hetflag, resseq, icode)
        return "<Residue %s het=%s resseq=%s icode=%s>" % full_id

    def strictly_equals(
        self: _ResidueT, other: _ResidueT, compare_coordinates: bool = False
    ) -> bool:
        """Compare this residue to the other residue using a strict definition of equality.

        The residues are equal if they have the same name, identifier,
        and their constituent atoms are strictly equal.

        :param other: The residue to compare this residue to
        :type other: Residue
        :param compare_coordinates: Whether to compare the coordinates of the atoms
        :type compare_coordinates: bool
        :return: Whether the residues are strictly equal
        :rtype: bool
        """
        if not isinstance(other, type(self)):
            return False

        return (
            self.resname == other.resname
            and self.id == other.id
            and Entity.strictly_equals(self, other, compare_coordinates)
        )

    def add(self, atom):
        """Add an Atom object.

        Checks for adding duplicate atoms, and raises a
        PDBConstructionException if so.
        """
        atom_id = atom.get_id()
        if self.has_id(atom_id):
            raise PDBConstructionException(
                f"Atom {atom_id} defined twice in residue {self}"
            )
        Entity.add(self, atom)

    def flag_disordered(self):
        """Set the disordered flag."""
        self.disordered = 1

    def is_disordered(self):
        """Return 1 if the residue contains disordered atoms."""
        return self.disordered

    def get_resname(self):
        """Return the residue name."""
        return self.resname

    def get_unpacked_list(self):
        """Return the list of all atoms, unpack DisorderedAtoms."""
        atom_list = self.get_list()
        undisordered_atom_list = []
        for atom in atom_list:
            if atom.is_disordered():
                undisordered_atom_list += atom.disordered_get_list()
            else:
                undisordered_atom_list.append(atom)
        return undisordered_atom_list

    def get_segid(self):
        """Return the segment identifier."""
        return self.segid

    def get_atoms(self):
        """Return atoms."""
        yield from self

    def mutate(self, mutate_to, sample_residue, selected_rotamer):
        """
        Mutates a given residue based on the best fitting rotamers
        :param mutate_to: Three letter amino acid code in uppercase letters
        :param sample_residue: Sample residue generated from a sampler RotamerSampling
        :param selected_rotamer: Selected rotamer generate from a sampler from RotamerSampling
        """
        if mutate_to not in ["ALA", "GLY"]:
            # Introduce the rotamer
            for angle in ["CHI1", "CHI2", "CHI3", "CHI4"]:
                if mutate_to not in CHI_ANGLES[angle]:
                    continue
                dihedral_start = calc_dihedral(
                    *[
                        Vector(sample_residue[x])
                        for x in CHI_ANGLES[angle][mutate_to]["ref_plane"]
                    ]
                )
                rotation_angle = dihedral_start - np.deg2rad(selected_rotamer[angle])
                axis = CHI_ANGLES[angle][mutate_to]["axis"]
                # print(angle)
                for atom in RESIDUE_ORDER[mutate_to][
                    RESIDUE_ORDER[mutate_to].index(axis[1]) + 1 :
                ]:
                    sample_residue[atom] = (
                        np.dot(
                            rotaxis2m(
                                rotation_angle,
                                Vector(
                                    sample_residue[axis[0]] - sample_residue[axis[1]]
                                ),
                            ),
                            sample_residue[atom] - sample_residue[axis[1]],
                        )
                        + sample_residue[axis[1]]
                    )
        for atom, coord in sample_residue.items():
            if atom not in ["C", "N", "CA", "O"]:
                new_atom = Atom(
                    name=atom,
                    element=atom[0],
                    fullname="{}{}".format(
                        " " * (4 - len(atom)), atom
                    ),  # for writing the structure, should be 4-char long
                    coord=np.asarray(coord),
                    bfactor=1.0,
                    altloc=" ",
                    occupancy=1.0,
                    serial_number=9999,  # does not matter much, only for writing the struct.
                )
                self.add(new_atom)
        self.resname = mutate_to


class DisorderedResidue(DisorderedEntityWrapper):
    """DisorderedResidue is a wrapper around two or more Residue objects.

    It is used to represent point mutations (e.g. there is a Ser 60 and a Cys 60
    residue, each with 50 % occupancy).
    """

    def __init__(self, id):
        """Initialize the class."""
        DisorderedEntityWrapper.__init__(self, id)

    def __repr__(self):
        """Return disordered residue full identifier."""
        if self.child_dict:
            resname = self.get_resname()
            hetflag, resseq, icode = self.get_id()
            full_id = (resname, hetflag, resseq, icode)
            return "<DisorderedResidue %s het=%s resseq=%i icode=%s>" % full_id
        else:
            return "<Empty DisorderedResidue>"

    def add(self, atom):
        """Add atom to residue."""
        residue = self.disordered_get()
        if atom.is_disordered() != 2:
            # Atoms in disordered residues should have non-blank
            # altlocs, and are thus represented by DisorderedAtom objects.
            resname = residue.get_resname()
            het, resseq, icode = residue.get_id()
            # add atom anyway, if PDBParser ignores exception the atom will be part of the residue
            residue.add(atom)
            raise PDBConstructionException(
                "Blank altlocs in duplicate residue %s (%s, %i, %s)"
                % (resname, het, resseq, icode)
            )
        residue.add(atom)

    def sort(self):
        """Sort the atoms in the child Residue objects."""
        for residue in self.disordered_get_list():
            residue.sort()

    def disordered_add(self, residue):
        """Add a residue object and use its resname as key.

        Arguments:
         - residue - Residue object

        """
        resname = residue.get_resname()
        # add chain parent to residue
        chain = self.get_parent()
        residue.set_parent(chain)
        assert not self.disordered_has_id(resname)
        self[resname] = residue
        self.disordered_select(resname)

    def disordered_remove(self, resname):
        """Remove a child residue from the DisorderedResidue.

        Arguments:
         - resname - name of the child residue to remove, as a string.

        """
        # Get child residue
        residue = self.child_dict[resname]
        is_selected = self.selected_child is residue

        # Detach
        del self.child_dict[resname]
        residue.detach_parent()

        if is_selected and self.child_dict:  # pick another selected_child
            child = next(iter(self.child_dict))
            self.disordered_select(child)
        elif not self.child_dict:  # no more children
            self.selected_child = None
