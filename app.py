"""
Linux File System Simulator — Single File Version
Run: pip install flask && python app_single.py
Open: http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template
import time, os, re

# ===============================================================================
# DISK + INODE
# ===============================================================================

TOTAL_BLOCKS  = 64
BLOCK_SIZE    = 512
SYSTEM_BLOCKS = 4

class Inode:
    def __init__(self, inode_num, name, size, strategy, blocks, content="", parent_path="/"):
        self.inode_num   = inode_num
        self.name        = name
        self.size        = size
        self.strategy    = strategy
        self.blocks      = blocks
        self.next_block  = {}
        self.index_block = None
        self.content     = content
        self.created_at  = time.strftime("%Y-%m-%d %H:%M:%S")
        self.file_type   = "d" if strategy == "dir" else "-"
        self.permissions = "rwxr-xr-x" if strategy == "dir" else "rw-r--r--"
        self.parent_path = parent_path
        self.children    = {}
        self.link_count  = 2 if strategy == "dir" else 1

    @property
    def full_path(self):
        if self.parent_path == "/" and self.name == "":
            return "/"
        if self.parent_path == "/":
            return "/" + self.name
        return self.parent_path + "/" + self.name

    def to_dict(self):
        return {
            "inode_num":   self.inode_num,
            "name":        self.name,
            "size":        self.size,
            "strategy":    self.strategy,
            "blocks":      self.blocks,
            "next_block":  self.next_block,
            "index_block": self.index_block,
            "content":     self.content,
            "created_at":  self.created_at,
            "file_type":   self.file_type,
            "permissions": self.permissions,
            "parent_path": self.parent_path,
            "full_path":   self.full_path,
            "children":    self.children,
            "link_count":  self.link_count,
        }


class Disk:
    def __init__(self):
        self.reset()

    def reset(self):
        self.blocks      = [None] * TOTAL_BLOCKS
        self.block_types = ["free"] * TOTAL_BLOCKS
        self.inode_table = {}
        self.next_inode  = 5
        self.cwd         = "/"
        self.path_index  = {}

        for i, label in enumerate(["superblock","block_bitmap","inode_bitmap","inode_table"]):
            self.blocks[i]      = label
            self.block_types[i] = "system"

        root = Inode(2, "", 4096, "dir", [], "", "/")
        root.file_type   = "d"
        root.permissions = "rwxr-xr-x"
        self.inode_table[2]  = root
        self.path_index["/"] = 2

    # path helpers
    def resolve(self, path):
        if not path or path == "~":
            return "/"
        if not path.startswith("/"):
            base = self.cwd if self.cwd != "/" else ""
            path = base + "/" + path
        parts = []
        for p in path.split("/"):
            if p == "" or p == ".":
                continue
            elif p == "..":
                if parts: parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)

    def inode_at(self, abs_path):
        inum = self.path_index.get(abs_path)
        return self.inode_table.get(inum) if inum is not None else None

    def resolve_inode(self, raw):
        return self.inode_at(self.resolve(raw))

    def parent_of(self, abs_path):
        p = "/".join(abs_path.rstrip("/").split("/")[:-1]) or "/"
        return self.inode_at(p)

    def get_free_blocks(self):
        return [i for i in range(SYSTEM_BLOCKS, TOTAL_BLOCKS) if self.blocks[i] is None]

    def free_blocks(self, blist):
        for b in blist:
            self.blocks[b]      = None
            self.block_types[b] = "free"

    def create_inode(self, abs_path, size, strategy, blocks, content=""):
        parts       = abs_path.rstrip("/").split("/")
        name        = parts[-1] if len(parts) > 1 else ""
        parent_path = "/".join(parts[:-1]) or "/"
        inode = Inode(self.next_inode, name, size, strategy, blocks, content, parent_path)
        self.inode_table[self.next_inode] = inode
        self.path_index[abs_path]         = self.next_inode
        parent = self.inode_at(parent_path)
        if parent:
            parent.children[name] = self.next_inode
        self.next_inode += 1
        return inode

    def remove_inode(self, abs_path):
        inum = self.path_index.pop(abs_path, None)
        if inum is None:
            return None
        inode = self.inode_table.pop(inum, None)
        if inode:
            parent = self.inode_at(inode.parent_path)
            if parent:
                parent.children.pop(inode.name, None)
        return inode

    def list_dir(self, abs_path):
        inode = self.inode_at(abs_path)
        if not inode or inode.file_type != "d":
            return None
        return [self.inode_table[inum] for inum in inode.children.values()
                if inum in self.inode_table]

    def to_dict(self):
        def build_tree(path):
            inode = self.inode_at(path)
            if not inode:
                return None
            node = inode.to_dict()
            if inode.file_type == "d":
                node["entries"] = []
                for cname in inode.children:
                    cp = (path.rstrip("/") + "/" + cname) if path != "/" else "/" + cname
                    ce = build_tree(cp)
                    if ce:
                        node["entries"].append(ce)
            return node

        return {
            "total_blocks":  TOTAL_BLOCKS,
            "block_size":    BLOCK_SIZE,
            "system_blocks": SYSTEM_BLOCKS,
            "blocks":        self.blocks,
            "block_types":   self.block_types,
            "inode_table":   {k: v.to_dict() for k, v in self.inode_table.items()},
            "path_index":    self.path_index,
            "cwd":           self.cwd,
            "tree":          build_tree("/"),
            "free_count":    len(self.get_free_blocks()),
            "used_count":    len(self.get_used_blocks()),
        }

    def get_used_blocks(self):
        return [i for i in range(SYSTEM_BLOCKS, TOTAL_BLOCKS) if self.blocks[i] is not None]


disk = Disk()

# ===============================================================================
# ALLOCATION STRATEGIES
# ===============================================================================

def alloc_contiguous(abs_path, size_kb, content=""):
    needed = max(1, size_kb)
    start = None; length = 0
    for i in range(SYSTEM_BLOCKS, TOTAL_BLOCKS):
        if disk.blocks[i] is None:
            if start is None: start = i
            length += 1
            if length == needed: break
        else:
            start = None; length = 0
    if length < needed:
        return {"error": f"Need {needed} contiguous free blocks, longest run is {length}."}
    chosen = list(range(start, start + needed))
    for b in chosen:
        disk.blocks[b] = abs_path; disk.block_types[b] = "data"
    inode = disk.create_inode(abs_path, size_kb * 1024, "contiguous", chosen, content)
    steps = [
        _s(1,"READ", [1], "Read block bitmap - scan for contiguous free run"),
        _s(2,"READ", [2], "Read inode bitmap - find free inode slot"),
        _s(3,"WRITE",[3], f"Write inode #{inode.inode_num} - start={start}, len={needed}"),
        _s(4,"WRITE",chosen, f"Write data blocks {chosen} - file content"),
        _s(5,"WRITE",[1], "Update block bitmap - mark blocks used"),
        _s(6,"WRITE",[2], "Update inode bitmap - mark inode used"),
    ]
    return {"success":True,"strategy":"contiguous","inode":inode.to_dict(),
            "allocated_blocks":chosen,"steps":steps,"disk":disk.to_dict()}


def alloc_linked(abs_path, size_kb, content=""):
    needed = max(1, size_kb)
    free   = disk.get_free_blocks()
    if len(free) < needed:
        return {"error": f"Need {needed} blocks, only {len(free)} free."}
    chosen = free[:needed]
    for b in chosen:
        disk.blocks[b] = abs_path; disk.block_types[b] = "data"
    inode = disk.create_inode(abs_path, size_kb * 1024, "linked", chosen, content)
    for i in range(len(chosen)-1):
        inode.next_block[chosen[i]] = chosen[i+1]
    inode.next_block[chosen[-1]] = -1
    chain = " -> ".join(str(b) for b in chosen) + " -> NULL"
    steps = [
        _s(1,"READ", [1], "Read block bitmap - collect any free blocks"),
        _s(2,"READ", [2], "Read inode bitmap - find free inode"),
        _s(3,"WRITE",[3], f"Write inode #{inode.inode_num} - head={chosen[0]}"),
        _s(4,"WRITE",chosen, f"Write blocks with next-pointers: {chain}"),
        _s(5,"WRITE",[1], "Update block bitmap"),
        _s(6,"WRITE",[2], "Update inode bitmap"),
    ]
    return {"success":True,"strategy":"linked","inode":inode.to_dict(),
            "allocated_blocks":chosen,"steps":steps,"disk":disk.to_dict()}


def alloc_indexed(abs_path, size_kb, content=""):
    needed = max(1, size_kb)
    free   = disk.get_free_blocks()
    if len(free) < needed + 1:
        return {"error": f"Need {needed+1} blocks (1 index + {needed} data), only {len(free)} free."}
    idx_blk   = free[0]
    data_blks = free[1:needed+1]
    all_blks  = [idx_blk] + data_blks
    for b in all_blks:
        disk.blocks[b] = abs_path; disk.block_types[b] = "data"
    disk.block_types[idx_blk] = "index"
    inode = disk.create_inode(abs_path, size_kb * 1024, "indexed", all_blks, content)
    inode.index_block = idx_blk
    steps = [
        _s(1,"READ", [1], "Read block bitmap - find index block + data blocks"),
        _s(2,"READ", [2], "Read inode bitmap - find free inode"),
        _s(3,"WRITE",[3], f"Write inode #{inode.inode_num} - pointer to index block {idx_blk}"),
        _s(4,"WRITE",[idx_blk], f"Write index block {idx_blk} - addresses {data_blks}"),
        _s(5,"WRITE",data_blks, f"Write data blocks {data_blks} - file content"),
        _s(6,"WRITE",[1], "Update block bitmap"),
        _s(7,"WRITE",[2], "Update inode bitmap"),
    ]
    return {"success":True,"strategy":"indexed","inode":inode.to_dict(),
            "allocated_blocks":all_blks,"steps":steps,"disk":disk.to_dict()}

# ===============================================================================
# LINUX COMMAND SIMULATOR
# ===============================================================================

def parse_command(cmd_string):
    parts = cmd_string.strip().split()
    if not parts:
        return _err("empty command")
    cmd  = parts[0]
    args = parts[1:]
    handlers = {
        "pwd":   cmd_pwd,
        "cd":    cmd_cd,
        "mkdir": cmd_mkdir,
        "rmdir": cmd_rmdir,
        "touch": cmd_touch,
        "cat":   cmd_cat,
        "ls":    cmd_ls,
        "rm":    cmd_rm,
        "cp":    cmd_cp,
        "mv":    cmd_mv,
        "stat":  cmd_stat,
        "echo":  cmd_echo,
        "chmod": cmd_chmod,
    }
    if cmd not in handlers:
        return _err(f"bash: {cmd}: command not found")
    return handlers[cmd](args)


# ── path traversal steps (used by every command) ──────────────────────────────
def psteps(abs_path):
    parts = [p for p in abs_path.split("/") if p]
    out = [_s(1,"READ",[2], "Read inode bitmap - begin path resolution"),
           _s(2,"READ",[3], "Read root inode #2 - start traversal at /")]
    for i, p in enumerate(parts):
        out.append(_s(3+i,"READ",[3], f"Read dir block - look up '{p}' -> get inode number"))
    return out


# permission checker
# permissions string: 9 chars e.g. "rw-r--r--"
# [0..2]=user [3..5]=group [6..8]=other
# We simulate as file owner so we check user bits (positions 0,1,2)

def _has_perm(inode, bit):
    idx = {"r":0, "w":1, "x":2}.get(bit, -1)
    if idx < 0:
        return True, inode.permissions
    return inode.permissions[idx] != "-", inode.permissions

def check_perm(inode, bit, cmd_name):
    allowed, perm = _has_perm(inode, bit)
    if allowed:
        return None
    action = {"r":"read","w":"write to","x":"execute/traverse"}.get(bit, "access")
    return _err(
        f"{cmd_name}: cannot {action} '{inode.name}': Permission denied\n"
        f"  Current permissions: {perm}\n"
        f"  Hint: chmod u+{bit} {inode.name}"
    )

def check_parent_perm(abs_path, bit, cmd_name):
    parent_path = "/".join(abs_path.split("/")[:-1]) or "/"
    parent = disk.inode_at(parent_path)
    if not parent:
        return None
    return check_perm(parent, bit, cmd_name)


# ── pwd ───────────────────────────────────────────────────────────────────────
def cmd_pwd(args):
    steps = [_s(1,"READ",[3], "Read process table - get cwd for current pid"),
             _s(2,"READ",[3], "Read cwd inode - build full path string")]
    return _ok(disk.cwd, steps, [])


# ── cd ────────────────────────────────────────────────────────────────────────
def cmd_cd(args):
    raw = args[0] if args else "/"
    abs_path = disk.resolve(raw)
    inode    = disk.inode_at(abs_path)
    ps       = psteps(abs_path)
    if not inode:
        return _err(f"cd: {raw}: No such file or directory")
    if inode.file_type != "d":
        return _err(f"cd: {raw}: Not a directory")
    if "x" not in inode.permissions:
        return _err(f"cd: {raw}: Permission denied")
    disk.cwd = abs_path
    ps.append(_s(len(ps)+1,"READ",[3],
               f"Check execute permission on '{inode.name}' - update process cwd to {abs_path}"))
    return _ok(f"(changed directory to {abs_path})", ps, inode.blocks)


# ── mkdir ─────────────────────────────────────────────────────────────────────
def cmd_mkdir(args):
    if not args:
        return _err("mkdir: missing operand")
    mkdir_p = "-p" in args
    dirs    = [a for a in args if not a.startswith("-")]
    if not dirs:
        return _err("mkdir: missing operand")

    all_steps  = []
    all_blocks = []
    created    = []

    for raw in dirs:
        abs_path = disk.resolve(raw)
        parts    = [p for p in abs_path.split("/") if p]

        if mkdir_p:
            current = "/"
            for part in parts:
                current = ("" if current == "/" else current) + "/" + part
                if disk.inode_at(current):
                    continue
                parent = disk.inode_at("/".join(current.split("/")[:-1]) or "/")
                if not parent or parent.file_type != "d":
                    return _err(f"mkdir: cannot create '{current}': parent not a directory")
                free = disk.get_free_blocks()
                if not free:
                    return _err("mkdir: no space left on device")
                db = free[0]
                disk.blocks[db] = current; disk.block_types[db] = "data"
                inode = disk.create_inode(current, 4096, "dir", [db], "")
                inode.file_type = "d"; inode.permissions = "rwxr-xr-x"
                n = len(all_steps)
                all_steps += [
                    _s(n+1,"READ", [2], f"Alloc inode for '{part}'"),
                    _s(n+2,"READ", [1], "Alloc dir data block"),
                    _s(n+3,"WRITE",[3], f"Write inode #{inode.inode_num} - path: {current}"),
                    _s(n+4,"WRITE",[db], f"Write dir block {db} - '.' and '..' entries"),
                    _s(n+5,"WRITE",[3], f"Update parent dir - add '{part}'"),
                ]
                all_blocks.append(db)
                created.append(current)
        else:
            if disk.inode_at(abs_path):
                return _err(f"mkdir: cannot create '{raw}': File exists")
            parent_path = "/".join(abs_path.split("/")[:-1]) or "/"
            parent      = disk.inode_at(parent_path)
            if not parent:
                return _err(f"mkdir: cannot create '{raw}': No such file or directory\n"
                            f"Hint: use 'mkdir -p {raw}' to create parent dirs too")
            denied = check_perm(parent, "w", "mkdir")
            if denied: return denied
            free = disk.get_free_blocks()
            if not free:
                return _err("mkdir: no space left on device")
            db = free[0]
            disk.blocks[db] = abs_path; disk.block_types[db] = "data"
            inode = disk.create_inode(abs_path, 4096, "dir", [db], "")
            inode.file_type = "d"; inode.permissions = "rwxr-xr-x"
            name = abs_path.split("/")[-1]
            ps   = psteps(parent_path)
            n    = len(ps)
            all_steps = ps + [
                _s(n+1,"READ", [2], "Read inode bitmap - find free inode"),
                _s(n+2,"READ", [1], "Read block bitmap - find free block"),
                _s(n+3,"WRITE",[3], f"Write inode #{inode.inode_num} - type=dir"),
                _s(n+4,"WRITE",[db], f"Write dir block {db} - '.' and '..' entries"),
                _s(n+5,"WRITE",[2], "Update inode bitmap"),
                _s(n+6,"WRITE",[1], "Update block bitmap"),
                _s(n+7,"WRITE",[3], f"Write parent dir - add '{name}'"),
            ]
            all_blocks = [db]
            created    = [abs_path]

    label = ", ".join(created) if created else "(all already existed)"
    return _ok(f"(created: {label})", all_steps, all_blocks)


# ── rmdir ─────────────────────────────────────────────────────────────────────
def cmd_rmdir(args):
    if not args:
        return _err("rmdir: missing operand")
    abs_path = disk.resolve(args[0])
    inode    = disk.inode_at(abs_path)
    if not inode:
        return _err(f"rmdir: '{args[0]}': No such file or directory")
    if inode.file_type != "d":
        return _err(f"rmdir: '{args[0]}': Not a directory")
    if inode.children:
        return _err(f"rmdir: '{args[0]}': Directory not empty\nHint: use 'rm -r {args[0]}'")
    denied = check_parent_perm(abs_path, "w", "rmdir")
    if denied: return denied
    blocks = list(inode.blocks)
    ps = psteps(abs_path)
    n  = len(ps)
    steps = ps + [
        _s(n+1,"READ", [3], f"Read inode #{inode.inode_num} - verify dir is empty"),
        _s(n+2,"WRITE",blocks, f"Free dir data blocks {blocks}"),
        _s(n+3,"WRITE",[1], "Update block bitmap"),
        _s(n+4,"WRITE",[2], f"Update inode bitmap - inode #{inode.inode_num} free"),
        _s(n+5,"WRITE",[3], f"Update parent dir - remove '{inode.name}'"),
    ]
    disk.free_blocks(blocks)
    disk.remove_inode(abs_path)
    return _ok(f"(removed directory {abs_path})", steps, blocks)


# ── touch ─────────────────────────────────────────────────────────────────────
def cmd_touch(args):
    if not args:
        return _err("touch: missing file operand")
    abs_path    = disk.resolve(args[0])
    parent_path = "/".join(abs_path.split("/")[:-1]) or "/"
    parent      = disk.inode_at(parent_path)
    if not parent:
        return _err(f"touch: '{args[0]}': No such file or directory")
    inode = disk.inode_at(abs_path)
    ps    = psteps(abs_path)
    n     = len(ps)
    if inode:
        denied = check_perm(inode, "w", "touch")
        if denied: return denied
        inode.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        steps = ps + [
            _s(n+1,"READ", [3], f"Read inode #{inode.inode_num} - file exists"),
            _s(n+2,"WRITE",[3], f"Write inode #{inode.inode_num} - update atime/mtime"),
        ]
        return _ok(f"(timestamps updated for {args[0]})", steps, inode.blocks)
    denied = check_parent_perm(abs_path, "w", "touch")
    if denied: return denied
    new_inode = disk.create_inode(abs_path, 0, "contiguous", [], "")
    name      = abs_path.split("/")[-1]
    steps = ps + [
        _s(n+1,"READ", [2], "Read inode bitmap - find free inode"),
        _s(n+2,"WRITE",[3], f"Write inode #{new_inode.inode_num} - size=0, no blocks"),
        _s(n+3,"WRITE",[2], "Update inode bitmap"),
        _s(n+4,"WRITE",[3], f"Write parent dir - add '{name}'"),
    ]
    return _ok(f"(created empty file {args[0]})", steps, [])


# ── cat ───────────────────────────────────────────────────────────────────────
def cmd_cat(args):
    if not args:
        return _err("cat: missing file operand")
    abs_path = disk.resolve(args[0])
    inode    = disk.inode_at(abs_path)
    if not inode:
        return _err(f"cat: {args[0]}: No such file or directory")
    if inode.file_type == "d":
        return _err(f"cat: {args[0]}: Is a directory")
    denied = check_perm(inode, "r", "cat")
    if denied: return denied
    ps = psteps(abs_path)
    n  = len(ps)
    steps = ps + [_s(n+1,"READ",[3], f"Read inode #{inode.inode_num} - block list: {inode.blocks}")]
    if not inode.blocks:
        steps.append(_s(n+2,"READ",[3], "Inode size=0, no data blocks - file is empty"))
        return _ok(f"(empty file: {args[0]})", steps, [])
    for i, b in enumerate(inode.blocks):
        steps.append(_s(n+2+i,"READ",[b], f"Read data block {b} - content chunk {i+1}"))
    return _ok(inode.content or f"(empty file: {args[0]})", steps, inode.blocks)


# ── ls ────────────────────────────────────────────────────────────────────────
def cmd_ls(args):
    flags   = [a for a in args if a.startswith("-")]
    targets = [a for a in args if not a.startswith("-")]
    path    = disk.resolve(targets[0]) if targets else disk.cwd
    long_f  = any("l" in f for f in flags)
    all_f   = any("a" in f for f in flags)
    inode   = disk.inode_at(path)
    if not inode:
        return _err(f"ls: cannot access '{targets[0] if targets else path}': No such file or directory")
    ps = psteps(path)
    n  = len(ps)
    if inode.file_type != "d":
        denied = check_perm(inode, "r", "ls")
        if denied: return denied
        steps = ps + [_s(n+1,"READ",[3], f"Read inode #{inode.inode_num} - single file stat")]
        line  = _fmt_ls(inode, long_f)
        return _ok(line, steps, inode.blocks)
    denied = check_perm(inode, "r", "ls")
    if denied: return denied
    entries = disk.list_dir(path) or []
    steps   = ps + [
        _s(n+1,"READ",[3], f"Read dir inode #{inode.inode_num} - find dir data block"),
        _s(n+2,"READ",inode.blocks, f"Read dir block - {len(entries)} entries"),
    ]
    for i, e in enumerate(entries):
        steps.append(_s(n+3+i,"READ",[3], f"Read inode #{e.inode_num} - metadata for {e.name}"))
    lines = []
    if all_f:
        lines += [".", ".."] if not long_f else [
            f"drwxr-xr-x 2 user 4096 {inode.created_at} .",
            f"drwxr-xr-x 2 user 4096 {inode.created_at} ..",
        ]
    for e in entries:
        lines.append(_fmt_ls(e, long_f))
    accessed = list({b for e in entries for b in e.blocks})
    return _ok("\n".join(lines) if lines else "(empty directory)", steps, accessed)

def _fmt_ls(inode, long_f):
    if long_f:
        return f"{inode.file_type}{inode.permissions}  {inode.link_count} user  {str(inode.size).rjust(6)}  {inode.created_at}  {inode.name}"
    return ("/" if inode.file_type=="d" else "") + inode.name


# ── rm ────────────────────────────────────────────────────────────────────────
def cmd_rm(args):
    if not args:
        return _err("rm: missing operand")
    recursive = any(f in args for f in ["-r","-rf","-fr","-R"])
    targets   = [a for a in args if not a.startswith("-")]
    if not targets:
        return _err("rm: missing operand")
    abs_path = disk.resolve(targets[0])
    inode    = disk.inode_at(abs_path)
    if not inode:
        return _err(f"rm: cannot remove '{targets[0]}': No such file or directory")
    if inode.file_type == "d" and not recursive:
        return _err(f"rm: cannot remove '{targets[0]}': Is a directory\nHint: use 'rm -r {targets[0]}'")
    # Check both: the file itself must be writable AND parent dir must allow unlinking
    denied = check_perm(inode, "w", "rm")
    if denied: return denied
    denied = check_parent_perm(abs_path, "w", "rm")
    if denied: return denied

    all_blocks = []
    ps         = psteps(abs_path)

    def _rm(path):
        nd = disk.inode_at(path)
        if not nd: return
        if nd.file_type == "d":
            for cname in list(nd.children.keys()):
                cp = (path if path == "/" else path) + ("/" if not path.endswith("/") else "") + cname
                _rm(cp)
        all_blocks.extend(nd.blocks)
        disk.free_blocks(nd.blocks)
        disk.remove_inode(path)

    _rm(abs_path)
    n  = len(ps)
    steps = ps + [
        _s(n+1,"WRITE",all_blocks, f"Free all data blocks {all_blocks}"),
        _s(n+2,"WRITE",[1], "Update block bitmap"),
        _s(n+3,"WRITE",[2], "Update inode bitmap - free all inodes"),
        _s(n+4,"WRITE",[3], f"Update parent dir - remove '{inode.name}'"),
    ]
    return _ok(f"(removed {targets[0]})", steps, all_blocks)


# ── chmod ─────────────────────────────────────────────────────────────────────
def _octal_to_perm(octal_str):
    result = ""
    for digit in octal_str[-3:]:
        n = int(digit)
        result += ("r" if n&4 else "-") + ("w" if n&2 else "-") + ("x" if n&1 else "-")
    return result

def _apply_symbolic(current, symbolic):
    perm  = list(current)   # 9 chars
    slots = {"u":[0,1,2],"g":[3,4,5],"o":[6,7,8],"a":[0,1,2,3,4,5,6,7,8]}
    order = ["r","w","x"]
    for part in symbolic.split(","):
        m = re.match(r'^([ugoa]*)([+\-=])([rwx]*)$', part.strip())
        if not m:
            return None, f"chmod: invalid mode: '{symbolic}'"
        who_str, op, what = m.group(1) or "a", m.group(2), m.group(3)
        indices = sorted({i for w in who_str for i in slots.get(w, [])})
        for idx in indices:
            char = order[idx % 3]
            if   op == "+": perm[idx] = char if char in what else perm[idx]
            elif op == "-": perm[idx] = "-"  if char in what else perm[idx]
            elif op == "=": perm[idx] = char if char in what else "-"
    return "".join(perm), None

def cmd_chmod(args):
    if len(args) < 2:
        return _err("chmod: missing operand\nUsage: chmod <mode> <path> [-R]\n"
                    "Modes: octal (755, 644) or symbolic (u+x, go-w, a=r, u+x,g-w)")
    recursive = "-R" in args or "-r" in args
    clean     = [a for a in args if not a.startswith("-")]
    if len(clean) < 2:
        return _err("chmod: missing operand")
    mode_str, target = clean[0], clean[1]
    abs_path = disk.resolve(target)
    inode    = disk.inode_at(abs_path)
    if not inode:
        return _err(f"chmod: cannot access '{target}': No such file or directory")

    def apply(nd):
        old = nd.permissions
        if re.match(r'^[0-7]{3,4}$', mode_str):
            nd.permissions = _octal_to_perm(mode_str)
            return old, nd.permissions, None
        new, err = _apply_symbolic(nd.permissions, mode_str)
        if err: return old, old, err
        nd.permissions = new
        return old, new, None

    ps      = psteps(abs_path)
    results = []
    errors  = []

    def _chmod_rec(path):
        nd = disk.inode_at(path)
        if not nd: return
        old, new, err = apply(nd)
        if err: errors.append(err); return
        results.append((nd, old, new))
        if recursive and nd.file_type == "d":
            for cname in nd.children:
                cp = path.rstrip("/") + "/" + cname
                _chmod_rec(cp)

    _chmod_rec(abs_path)
    if errors:
        return _err(errors[0])

    n     = len(ps)
    steps = ps[:]
    for i, (nd, old, new) in enumerate(results):
        steps.append(_s(n+1+i,"WRITE",[3],
            f"Write inode #{nd.inode_num} ({nd.name}): {old} -> {new}"))

    lines = [f"{nd.full_path}: {old} -> {new}" for nd, old, new in results]
    all_blocks = list({b for nd,_,__ in results for b in nd.blocks})
    return _ok("\n".join(lines), steps, all_blocks)


# ── cp ────────────────────────────────────────────────────────────────────────
def cmd_cp(args):
    if len(args) < 2:
        return _err("cp: missing destination operand")
    src_raw = args[-2]; dst_raw = args[-1]
    src = disk.resolve(src_raw)
    dst = disk.resolve(dst_raw)
    f   = disk.inode_at(src)
    if not f:
        return _err(f"cp: cannot stat '{src_raw}': No such file or directory")
    if f.file_type == "d":
        return _err("cp: omitting directory (use -r for recursive copy - not yet supported)")
    denied = check_perm(f, "r", "cp")
    if denied: return denied
    dst_node = disk.inode_at(dst)
    if dst_node and dst_node.file_type == "d":
        dst = dst.rstrip("/") + "/" + f.name
    elif dst_node:
        return _err(f"cp: '{dst_raw}' already exists")
    dst_parent_path = "/".join(dst.split("/")[:-1]) or "/"
    if not disk.inode_at(dst_parent_path):
        return _err(f"cp: cannot create '{dst_raw}': No such directory")
    needed   = max(1, len(f.blocks))
    free     = disk.get_free_blocks()
    if len(free) < needed:
        return _err("cp: not enough free blocks")
    new_blks = free[:needed]
    for b in new_blks:
        disk.blocks[b] = dst; disk.block_types[b] = "data"
    ni = disk.create_inode(dst, f.size, f.strategy, new_blks, f.content)
    ps = psteps(src)
    n  = len(ps)
    steps = ps + [_s(n+1,"READ",[3], f"Read inode #{f.inode_num} - blocks {f.blocks}")]
    for i, b in enumerate(f.blocks):
        steps.append(_s(n+2+i,"READ",[b], f"Read source block {b}"))
    b2 = n+2+len(f.blocks)
    steps += [
        _s(b2,   "READ", [2],      "Allocate new inode for destination"),
        _s(b2+1, "READ", [1],      "Allocate new data blocks"),
        _s(b2+2, "WRITE",[3],      f"Write inode #{ni.inode_num} - destination metadata"),
        _s(b2+3, "WRITE",new_blks, f"Write new blocks {new_blks} - copy content"),
        _s(b2+4, "WRITE",[3],      f"Write parent dir - add '{dst.split('/')[-1]}'"),
    ]
    return _ok(f"(copied {src_raw} -> {dst_raw})", steps, f.blocks + new_blks)


# ── mv ────────────────────────────────────────────────────────────────────────
def cmd_mv(args):
    if len(args) < 2:
        return _err("mv: missing destination operand")
    src_raw = args[-2]; dst_raw = args[-1]
    src = disk.resolve(src_raw)
    dst = disk.resolve(dst_raw)
    f   = disk.inode_at(src)
    if not f:
        return _err(f"mv: cannot stat '{src_raw}': No such file or directory")
    denied = check_parent_perm(src, "w", "mv")
    if denied: return denied
    dst_node = disk.inode_at(dst)
    if dst_node and dst_node.file_type == "d":
        dst = dst.rstrip("/") + "/" + f.name
    dst_parent_path = "/".join(dst.split("/")[:-1]) or "/"
    if not disk.inode_at(dst_parent_path):
        return _err(f"mv: cannot move to '{dst_raw}': No such directory")
    old_blocks   = list(f.blocks)
    old_path     = src
    old_parent   = disk.inode_at(f.parent_path)
    if old_parent: old_parent.children.pop(f.name, None)
    disk.path_index.pop(old_path, None)
    new_name        = dst.split("/")[-1]
    new_parent_path = "/".join(dst.split("/")[:-1]) or "/"
    f.name          = new_name
    f.parent_path   = new_parent_path
    disk.path_index[dst] = f.inode_num
    new_parent = disk.inode_at(new_parent_path)
    if new_parent: new_parent.children[new_name] = f.inode_num
    for b in f.blocks:
        disk.blocks[b] = dst
    ps = psteps(src)
    n  = len(ps)
    steps = ps + [
        _s(n+1,"READ", [3], f"Read inode #{f.inode_num} - verify metadata"),
        _s(n+2,"WRITE",[3], f"Write old parent dir - remove '{src.split('/')[-1]}'"),
        _s(n+3,"WRITE",[3], f"Write new parent dir - add '{new_name}' (same inode, no data copy)"),
        _s(n+4,"WRITE",[3], f"Write inode #{f.inode_num} - update name and parent path"),
    ]
    return _ok(f"(moved {src_raw} -> {dst_raw})", steps, old_blocks)


# ── stat ─────────────────────────────────────────────────────────────────────
def cmd_stat(args):
    if not args:
        return _err("stat: missing operand")
    abs_path = disk.resolve(args[0])
    f = disk.inode_at(abs_path)
    if not f:
        return _err(f"stat: cannot stat '{args[0]}': No such file or directory")
    denied = check_perm(f, "r", "stat")
    if denied: return denied
    ps = psteps(abs_path)
    n  = len(ps)
    steps = ps + [_s(n+1,"READ",[3], f"Read inode #{f.inode_num} - all metadata fields")]
    out = (f"  File: {f.full_path}\n"
           f"  Size: {f.size}\t\tBlocks: {len(f.blocks)}\tIO Block: 512\n"
           f"  Type: {'directory' if f.file_type=='d' else 'regular file'}\n"
           f"  Inode: {f.inode_num}\tLinks: {f.link_count}\n"
           f"  Access: ({f.permissions})\n"
           f"  Modify: {f.created_at}\n"
           f"  Strategy: {f.strategy}\n"
           f"  Block list: {f.blocks}")
    return _ok(out, steps, f.blocks)


# ── echo ─────────────────────────────────────────────────────────────────────
def cmd_echo(args):
    if ">" not in args:
        return _ok(" ".join(args).strip('"').strip("'"), [], [])
    idx      = args.index(">")
    content  = " ".join(args[:idx]).strip('"').strip("'")
    name     = args[idx+1] if idx+1 < len(args) else None
    if not name:
        return _err("echo: missing filename after '>'")
    abs_path = disk.resolve(name)
    parent_path = "/".join(abs_path.split("/")[:-1]) or "/"
    if not disk.inode_at(parent_path):
        return _err(f"echo: {name}: No such file or directory")
    f  = disk.inode_at(abs_path)
    ps = psteps(abs_path)
    n  = len(ps)
    if f:
        denied = check_perm(f, "w", "echo")
        if denied: return denied
        if f.blocks:
            steps = ps + [
                _s(n+1,"READ", [3],      f"Read inode #{f.inode_num} - block list {f.blocks}"),
                _s(n+2,"WRITE",f.blocks, f"Overwrite data blocks {f.blocks} - new content"),
                _s(n+3,"WRITE",[3],      f"Write inode #{f.inode_num} - update size, timestamp")]
            f.content = content; f.size = len(content)
            return _ok(f"(wrote to {name})", steps, f.blocks)
        else:
            free = disk.get_free_blocks()
            if not free: return _err("echo: no space left on device")
            nb = free[0]
            disk.blocks[nb] = abs_path; disk.block_types[nb] = "data"
            f.blocks = [nb]; f.content = content; f.size = len(content)
            steps = ps + [
                _s(n+1,"READ", [3],  f"Read inode #{f.inode_num} - file empty, need block"),
                _s(n+2,"READ", [1],  "Read block bitmap - allocate data block"),
                _s(n+3,"WRITE",[nb], f"Write data block {nb} - content"),
                _s(n+4,"WRITE",[3],  f"Write inode #{f.inode_num} - update block ptr, size")]
            return _ok(f"(wrote to {name})", steps, [nb])
    # new file - check parent dir write permission
    denied = check_parent_perm(abs_path, "w", "echo")
    if denied: return denied
    free = disk.get_free_blocks()
    if not free: return _err("echo: no space left on device")
    nb = free[0]
    disk.blocks[nb] = abs_path; disk.block_types[nb] = "data"
    inode = disk.create_inode(abs_path, len(content), "contiguous", [nb], content)
    steps = ps + [
        _s(n+1,"READ", [2],  "Read inode bitmap - allocate inode"),
        _s(n+2,"READ", [1],  "Read block bitmap - allocate data block"),
        _s(n+3,"WRITE",[3],  f"Write inode #{inode.inode_num} - new file metadata"),
        _s(n+4,"WRITE",[nb], f"Write data block {nb} - content"),
        _s(n+5,"WRITE",[3],  f"Write parent dir - add '{abs_path.split('/')[-1]}'")]
    return _ok(f"(created {name} with content)", steps, [nb])


# ── helpers ───────────────────────────────────────────────────────────────────
def _s(num, op, blocks, desc):
    return {"step": num, "type": op, "blocks": blocks, "desc": desc}

def _ok(output, steps, accessed):
    return {"output": output, "steps": steps,
            "accessed_blocks": list(set(accessed)), "disk": disk.to_dict()}

def _err(msg):
    return {"error": msg, "output": msg, "steps": [],
            "accessed_blocks": [], "disk": disk.to_dict()}

# ===============================================================================
# FLASK APP
# ===============================================================================

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/api/disk')
def get_disk():
    return jsonify(disk.to_dict())

@app.route('/api/allocate', methods=['POST'])
def allocate():
    d        = request.json
    raw_path = d.get('filename','').strip()
    size_kb  = int(d.get('size_kb',1))
    strategy = d.get('strategy','contiguous')
    content  = d.get('content','')
    if not raw_path:           return jsonify({"error":"Path is required"}),400
    if not 1<=size_kb<=20:     return jsonify({"error":"Size must be 1-20 KB"}),400
    abs_path = disk.resolve(raw_path)
    parent_p = "/".join(abs_path.split("/")[:-1]) or "/"
    if not disk.inode_at(parent_p):
        return jsonify({"error":f"Parent dir '{parent_p}' does not exist.\nHint: mkdir -p '{parent_p}'"}),400
    if disk.inode_at(abs_path):
        return jsonify({"error":f"'{raw_path}' already exists"}),400
    fn={"contiguous":alloc_contiguous,"linked":alloc_linked,"indexed":alloc_indexed}.get(strategy)
    if not fn: return jsonify({"error":f"Unknown strategy: {strategy}"}),400
    result=fn(abs_path,size_kb,content)
    if "error" in result: return jsonify(result),400
    return jsonify(result)

@app.route('/api/delete', methods=['POST'])
def delete_file():
    raw=request.json.get('filename','').strip()
    abs_path=disk.resolve(raw)
    inode=disk.inode_at(abs_path)
    if not inode: return jsonify({"error":f"'{raw}' not found"}),404
    blocks=list(inode.blocks)
    disk.free_blocks(blocks)
    disk.remove_inode(abs_path)
    return jsonify({"success":True,"freed_blocks":blocks,"disk":disk.to_dict()})

@app.route('/api/reset', methods=['POST'])
def reset():
    disk.reset()
    return jsonify({"success":True,"disk":disk.to_dict()})

@app.route('/api/command', methods=['POST'])
def run_command():
    cmd=request.json.get('command','').strip()
    if not cmd: return jsonify({"error":"No command"}),400
    return jsonify(parse_command(cmd))

if __name__=='__main__':
    print("Linux FS Simulator -> http://localhost:5000")
    app.run(debug=True,port=5002)