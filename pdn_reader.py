import struct
import gzip
import StringIO



class PDNDocument(object):
    def __init__(self, width=None, height=None, layers=None):
        self.width = width
        self.height = height
        self.layers = layers
        
    def from_dict(self, values):
        self.__init__(values['width'], values['height'], values['layers'])


class PDNLayerList(list):
    def from_dict(self, values):
        self.extend(values['ArrayList+_items'][:values['ArrayList+_size']])


class PDNBitmapLayer(object):
    def __init__(self, width=None, height=None, layer_properties=None, surface=None, properties=None):
        self.width = width
        self.height = height
        self.layer_properties = layer_properties
        self.surface = surface
        self.properties = properties
        
    def from_dict(self, values):
        self.__init__(values['Layer+width'], values['Layer+height'], values['Layer+properties'],
                      values['surface'], values['properties'])


class PDNSurface(object):
    def __init__(self, width=None, height=None, stride=None, data=None):
        self.width = width
        self.height = height
        self.stride = stride
        self.data = data
        
    def from_dict(self, values):
        self.__init__(values['width'], values['height'], values['stride'],
                      values['scan0'].data)


class PDNDict(dict):
    def from_dict(self, values):
        self.update(zip(values['Keys'],values['Values']))


class PDNList(list):
    def from_dict(self, values):
        self.extend(values['_items'][:values['_size']])

CLASSES = {
    'PaintDotNet.Document': PDNDocument,
    'PaintDotNet.LayerList': PDNLayerList,
    'PaintDotNet.BitmapLayer': PDNBitmapLayer,
    'PaintDotNet.Surface': PDNSurface,
    'System.Collections.Specialized.NameValueCollection': PDNDict,
    'System.Collections.ArrayList': PDNList,
}

class Object(object):
    pass

class AbstractClassWithMembers(object):
    def __init__(self, stream, is_system=False):
        self.object_id, = stream.read_struct('i')
        self.name = stream.read_string()
        member_count, = stream.read_struct('i')
        members = [stream.read_string() for _ in xrange(member_count)]
        type_info = stream.read_struct('b'*member_count)
        additional = [stream.read_type_info(info) for info in type_info]
        self.members = zip(members,type_info,additional)
        self.library_id, = stream.read_struct('i') if not is_system else (None,)
        self.values = dict((name, stream.read_type_with_info(info,add)) for name,info,add in self.members)
        self.post_deserialize(stream)
        
    def post_deserialize(self, stream):
        if self.name == 'PaintDotNet.MemoryBlock':
            if self.values.get('deferred'):
                stream.deferred_objects.append(self)
            
    def deserialize(self, stream):
        length = self.values.get('length64')
        format_version, = stream.read_struct('B')
        assert format_version in (0,1)
        chunk_size, = stream.read_struct2('I')
        chunk_count = (length+chunk_size-1)//chunk_size
        chunks = [None]*chunk_count
        for _ in xrange(chunk_count):
            chunk_number, data_size= stream.read_struct2('II')
            assert chunks[chunk_number] is None, "already encountered chunk #%d"%chunk_number
            chunks[chunk_number]=True
            chunk_offset = chunk_number * chunk_size
            this_chunk_size = min(chunk_size, length-chunk_offset)
            compressed_bytes = stream.read(data_size)
            if format_version == 0:
                compressed_bytes = gzip.GzipFile(fileobj=StringIO.StringIO(compressed_bytes)).read()
            assert len(compressed_bytes) == this_chunk_size
            chunks[chunk_number] = compressed_bytes
        self.values['data']=''.join(chunks)

    def to_python(self, stream):
        obj = CLASSES.get(self.name,Object)()
        stream.pyobjects[self]=obj
        if hasattr(obj,'from_dict'):
            obj.from_dict(dict(
                (name, stream.get_object(val))
                for name, val in self.values.iteritems()
            ))
        else:
            obj.__name = self.name
            for name, val in self.values.iteritems():
                setattr(obj, name, stream.get_object(val))
        return obj

class ClassWithMembersAndTypes(AbstractClassWithMembers):
    pass

class SystemClassWithMembersAndTypes(AbstractClassWithMembers):
    def __init__(self, stream):
        AbstractClassWithMembers.__init__(self, stream, True)


class ClassWithId(AbstractClassWithMembers):
    def __init__(self, stream):
        self.object_id, = stream.read_struct('i')
        metadata_id, = stream.read_struct('i')
        cls = stream.objects[metadata_id]
        self.members = cls.members
        self.name = cls.name
        self.library_id = cls.library_id
        self.values = dict((name, stream.read_type_with_info(info,add)) for name,info,add in self.members)
        self.post_deserialize(stream)

class MemberReference(object):
    def __init__(self, stream):
        self.id_ref, = stream.read_struct('i')

    def to_python(self, stream):
        return stream.get_object(stream.objects[self.id_ref])

class BinaryArray(object):
    def __init__(self, stream):
        self.object_id, = stream.read_struct('i')
        binary_array_type, rank = stream.read_struct('bi')
        lengths = stream.read_struct('i'*rank)
        self.lower_bounds = stream.read_struct('i'*rank) if binary_array_type in (3,4,5) else None
        info, = stream.read_struct('b')
        additional = stream.read_type_info(info)
        def read_array(lengths):
            if len(lengths)>1:
                return [read_array(lengths[1:]) for _ in xrange(lengths[0])]
            return [stream.read_type_with_info(info,additional) for _ in xrange(lengths[0])]
        self.values = read_array(lengths)
        
    def to_python(self, stream):
        def to_array(values):
            return [to_array(val) for val in values] if isinstance(values, list) else stream.get_object(values)
        return to_array(self.values)
    
class ArraySingleObject(object):
    def __init__(self, stream):
        self.object_id, = stream.read_struct('i')
        length, = stream.read_struct('i')
        self.values = [stream.read_type_with_info(1, None) for _ in xrange(length)]

    def to_python(self, stream):
        return [stream.get_object(val) for val in self.values]

class BinaryFormat(object):

    def object_null(self):
        return None
    
    def object_null_multiple(self):
        cnt, = self.read_struct('I')
        self.null_cnt = cnt-1
        return None
    
    def object_null_multiple256(self):
        cnt, = self.read_struct('B')
        self.null_cnt = cnt-1
        return None
    
    def message_end(self):
        raise StopIteration()
    
    def serialized_stream_header(self):
        self.root_id, self.header_id, self.major_version, self.minor_version = self.read_struct('IIII')
        return None

    def binary_library(self):
        library_id, = self.read_struct('I')
        self.libraries[library_id] = self.read_string()
        return None

    def binary_string(self):
        object_id, = self.read_struct('i')
        result = self.read_string()
        self.objects[object_id] = result
        return result
    
    RECORDS = {
        0: serialized_stream_header, # Identifies the SerializationHeaderRecord.
        1: ClassWithId, # Identifies a ClassWithId record.
        #2: SystemClassWithMembers, # Identifies a SystemClassWithMembers record.
        #3: ClassWithMembers, # Identifies a ClassWithMembers record.
        4: SystemClassWithMembersAndTypes, # Identifies a SystemClassWithMembersAndTypes record.
        5: ClassWithMembersAndTypes, # Identifies a ClassWithMembersAndTypes record.
        6: binary_string, # Identifies a BinaryObjectString record.
        7: BinaryArray, # Identifies a BinaryArray record.
        # 8: MemberPrimitiveTyped, # Identifies a MemberPrimitiveTyped record.
        9: MemberReference, # Identifies a MemberReference record.
        10: object_null, # Identifies an ObjectNull record.
        11: message_end, # Identifies a MessageEnd record.
        12: binary_library, #Identifies a BinaryLibrary record.
        13: object_null_multiple256, # Identifies an ObjectNullMultiple256 record.
        14: object_null_multiple, # Identifies an ObjectNullMultiple record
        #15: ArraySinglePrimitive, # Identifies an ArraySinglePrimitive.
        16: ArraySingleObject, # Identifies an ArraySingleObject record.
        17: ArraySingleObject, # Identifies an ArraySingleString record.
        #21: MethodCall, # Identifies a BinaryMethodCall record.
        #22: MethodReturn, # Identifies a BinaryMethodReturn record.
    }
    
    
    def __init__(self, stream):
        self.stream = stream
        self.libraries = {}
        self.objects = {}
        self.pyobjects = {None:None}
        self.deferred_objects = []
        self.null_cnt = 0
        self.root_id, self.header_id, self.major_version, self.minor_version = 0,0,0,0

    def deserialize(self):
        try:
            while True:
                self.read_record()
        except StopIteration:
            pass
        for obj in self.deferred_objects:
            obj.deserialize(self)
        result = self.get_object(self.objects[self.root_id])
        return result
    
    def get_object(self, obj):
        if obj in self.pyobjects:
            return self.pyobjects[obj]
        pyobj = obj.to_python(self) if hasattr(obj,'to_python') else obj
        self.pyobjects[obj]=pyobj
        return pyobj
    
    def read_record(self):
        if self.null_cnt>0:
            self.null_cnt -= 1
            return None
        record_type = self.stream.read(1)
        result = self.RECORDS[ord(record_type)](self)
        obj_id = getattr(result,'object_id', None)
        self.objects[obj_id] = result
        return result
    
    def read(self, size):
        return self.stream.read(size)
    
    def read_struct(self, format):  # @ReservedAssignment
        size = struct.calcsize('<'+format)
        return struct.unpack('<'+format, self.stream.read(size))

    def read_struct2(self, format):  # @ReservedAssignment
        size = struct.calcsize('>'+format)
        return struct.unpack('>'+format, self.stream.read(size))

    def read_string(self):
        length, bits = 0,0
        while True:
            byte = ord(self.stream.read(1))
            length += (byte&0x7F)<<bits
            if byte&0x80==0:
                break
            bits +=7
        return self.stream.read(length)
    
    def read_type_info(self, info):
        if info in (0,7):
            return ord(self.stream.read(1))
        elif info in (1,2,5,6):
            return None
        elif info == 3:
            return self.read_string()
        elif info == 4:
            return self.read_string(), self.read_struct('i')[0]
        else:
            raise AssertionError("unknown info-type %02x"%info)

    def read_type_with_info(self, info, additional):
        if info==0:
            return self.read_primitive_type(additional)
        elif info in (1,2,3,4,5,6):
            return self.read_record()
        else:
            raise AssertionError("unknown info-type %02x"%info)


    PRIMITIVE_TYPE_FORMAT = {
        1:"?", 2: 'B',
        6:'d', 7: 'h', 8: 'i', 9: 'q', 10: 'b',
        11: 'f',
        14: 'H', 15: 'I', 16: 'Q',
    }
    def read_primitive_type(self, primitive_type):
        return self.read_struct(self.PRIMITIVE_TYPE_FORMAT[primitive_type])[0]

MAGIC_BYTES="PDN3"

def pdn_reader(stream):
    if not getattr(stream,'read',None):
        with open(stream,'rb') as stream:
            return pdn_reader(stream)
    
    pdn21format = False
    # Version 2.1+ file format:
    #   Starts with bytes as defined by MagicBytes 
    #   Next three bytes are 24-bit unsigned int 'N' (first byte is low-word, second byte is middle-word, third byte is high word)
    #   The next N bytes are a string, this is the document header (it is XML, UTF-8 encoded)
    #       Important: 'N' indicates a byte count, not a character count. 'N' bytes may result in less than 'N' characters,
    #                  depending on how the characters decode as per UTF8
    #   If the next 2 bytes are 0x00, 0x01: This signifies that non-compressed .NET serialized data follows.
    #   If the next 2 bytes are 0x1f, 0x8b: This signifies the start of the gzip compressed .NET serialized data
    #
    # Version 2.0 and previous file format:
    #   Starts with 0x1f, 0x8b: this signifies the start of the gzip compressed .NET serialized data.

    gzip_flag = stream.read(2)
    header_xml = None 
    if gzip_flag == MAGIC_BYTES[:2]:
        magic = stream.read(len(MAGIC_BYTES)-2)
        assert magic == MAGIC_BYTES[2:]

        # Read in the header if we found the 'magic' bytes identifying a PDN 2.1 file
        length = struct.unpack("<I",stream.read(3)+'\0')[0]
        header_xml = stream.read(length)
        gzip_flag = stream.read(2)
    
    if gzip_flag == '\x00\x01':
        pass
    elif gzip_flag == '\x1f\x8b':
        stream = gzip.GzipFile(mode="rb", fileobj=stream)
    else:
        assert False, gzip_flag.encode('hex')
    return BinaryFormat(stream).deserialize()

import png
import numpy

if __name__=='__main__':
    result = pdn_reader("test.pdn")
    images = []
    for idx,layer in enumerate(result.layers):
        data =numpy.fromstring(layer.surface.data, dtype='B')
        data = data.reshape(-1,layer.surface.stride//4,4)
        print layer.layer_properties.name, data.shape
        data[:,:,[0,2]]=data[:,:,[2,0]]
        data = data.reshape(-1,layer.surface.stride)
        img = png.from_array(data,'RGBA',{'width':layer.width,'height':layer.height})
        out = StringIO.StringIO()
        img.save(out)
        images.append((layer.layer_properties.name,out.getvalue()))
    html="""<html>
<script src="jquery.js"></script>
<style>.image_container { position:relative; width: %spx; height:%spx }
.image_container img { position:absolute;left:0px;top:0px }
.image_container .layers { display:none; position:absolute;right:5px;top:5px;padding:5px;border:1px solid black; background: rgba(255,255,255,0.5) }
.image_container:hover .layers { display:block }</style>
<body><div class="image_container">%s<div class="layers">Layers:<br/>%s</div></div></body></html>
"""%(result.width, result.height,
     ''.join('<img title="{name}" src="data:image/png;base64,{data}">'.format(name=name,data=data.encode("base64").replace("\n", "")) 
        for name, data in images),
     ''.join("""<input type="checkbox" checked="checked" onclick="$('img[title=&quot;%s&quot;]').toggle()">%s<br/>"""%(name,name) for name,data in images)
)                                                           
    open('test.html','wb').write(html)